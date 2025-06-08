import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
from classes.data_manager import DataManager
from classes.channel_status import ChannelStatus
from classes.helpers import Helper
from classes.cache import Cache
from classes.ticket_opener import TicketOpener
from classes.rate_limiter import Queue
from classes.ticket_creator import DMCategoryButtonView, TicketRatingView
from classes.error_handler import *
from utils import emojis, checks
from utils.logger import *


bot_token = os.getenv("BOT_TOKEN")
owners = list(map(int, os.getenv("OWNERS").split(",")))

startup = True
ready = True

class Mantid(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()  # Start with default intents
        intents.messages = True  
        intents.guilds = True  
        intents.dm_messages = True  
        intents.message_content = True 
        description = ""

        # Create bot instance with command prefix
        super().__init__(command_prefix=commands.when_mentioned_or('+'), intents=intents, description=description, help_command=None)
        self.data_manager = DataManager(self)
        self.channel_status = ChannelStatus(self)
        self.helper = Helper(self)
        self.cache = Cache(self)
        self.opener = TicketOpener(self)
        self.queue = Queue()
        self.api_patched = False


    # Monkey-patch discord.py http calls to use the Queue class
    def patch_api_routes(self, queue):
        if getattr(self, "api_patched", False):
            return
        self.api_patched = True

        # Save originals
        global original_send, original_edit, original_fetch_member, original_fetch_user
        global original_delete, original_add_reaction, original_fetch_channel

        original_send = discord.abc.Messageable.send
        original_edit = discord.Message.edit
        original_delete = discord.Message.delete
        original_fetch_member = discord.Guild.fetch_member
        original_fetch_user = discord.Client.fetch_user
        original_fetch_channel = discord.Client.fetch_channel
        original_add_reaction = discord.Message.add_reaction

        # Monkey patch
        async def queued_send(self_, *args, **kwargs):
            return await queue.call(original_send, self_, *args, **kwargs, route_type='message_send')

        async def queued_edit(self_, *args, **kwargs):
            return await queue.call(original_edit, self_, *args, **kwargs, route_type='message_edit')

        async def queued_delete(self_, *args, **kwargs):
            return await queue.call(original_delete, self_, *args, **kwargs, route_type='message_delete')

        async def queued_fetch_member(self_, user_id, *args, **kwargs):
            return await queue.call(original_fetch_member, self_, user_id, *args, **kwargs, route_type='fetch_member')

        async def queued_fetch_user(self_, user_id, *args, **kwargs):
            return await queue.call(original_fetch_user, self_, user_id, *args, **kwargs, route_type='fetch_user')

        async def queued_fetch_channel(self_, channel_id, *args, **kwargs):
            return await queue.call(original_fetch_channel, self_, channel_id, *args, **kwargs, route_type='fetch_generic')

        async def queued_add_reaction(self_, emoji, *args, **kwargs):
            return await queue.call(original_add_reaction, self_, emoji, *args, **kwargs, route_type='add_reaction')

        # Apply patches
        discord.abc.Messageable.send = queued_send
        discord.Message.edit = queued_edit
        discord.Message.delete = queued_delete
        discord.Message.add_reaction = queued_add_reaction
        discord.Guild.fetch_member = queued_fetch_member
        discord.Client.fetch_user = queued_fetch_user
        discord.Client.fetch_channel = queued_fetch_channel
    
    
    async def on_ready(self):
        global ready
        global startup

        logger.log("SYSTEM", "------- STARTUP INITIATED ----------------")
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for tickets!"))

        logger.log("SYSTEM", "------- FETCHING DATA --------------------")
        if startup:
            self.patch_api_routes(self.queue)
            if self.data_manager.db_pool is None:
                try:
                    await self.data_manager.connect_to_db()
                except Exception as e:
                    ready = False
                    logger.critical(f"All database re-connect attempts failed: {e}")
                    await self.close()
                if self.data_manager.db_pool is not None:
                    await self.data_manager.data_startup()
                    heartbeat.start()
                if not hasattr(bot, "persistent_views_added"):
                    logger.log("SYSTEM", "------- ADDING PERSISTENT VIEWS ----------")
                    bot.add_view(DMCategoryButtonView(bot))
                    bot.add_view(TicketRatingView(bot))
                    bot.persistent_views_added = True
                startup = False
        
        logger.log("SYSTEM", "------- LOADING COGS ---------------------")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                 # Attempt to load each cog, ignore if already loaded
                if (f'cogs.{filename[:-3]}') in self.extensions:
                    logger.info(f"Already loaded cog: {filename}")
                else:  
                    try:
                        await bot.load_extension(f'cogs.{filename[:-3]}')
                        logger.success(f"Loaded cog: {filename}")
                    except Exception as e:
                        ready = False
                        logger.exception(f"Failed to load {filename}: {e}")

        # Prints READY ASCII text         
        if ready:
            logger.log("NOTIF", "\n  ___   ___     _     ___   __   __"
                                "\n | _ \ | __|   /_\   |   \  \ \ / /"
                                "\n |   / | _|   / _ \  | |) |  \ V / "
                                "\n |_|_\ |___| /_/ \_\ |___/    |_|  "
                                "\n                                   ")
            logger.log("SYSTEM", f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        else:
            logger.critical("❌❌❌ Bot experienced core failures: Resolve listed errors before further use ❌❌❌")
            await super().close()


    # Shuts down database, redis, and workers before bot shutdown
    async def on_close(self):
        logger.log("SYSTEM", "------- SHUTTING DOWN --------------------")
        
        heartbeat.cancel()
        await self.data_manager.data_shutdown()
        await super().close()

bot = Mantid()
bot.patch_api_routes(bot.queue)


# Sends a small query every 10 minutes to catch inactivity disconnects
@tasks.loop(minutes=10)
async def heartbeat():
    status = await bot.data_manager.check_db_health()
    if not status:
        if bot.data_manager.db_pool is None:
            await bot.data_manager.connect_to_db()


# Save channel_status dictionaries to cache every 2 minutes
# @tasks.loop(minutes=2)
# async def autosave():
#     await bot.data_manager.save_status_dicts_to_redis()
#     await bot.data_manager.save_timers_to_redis()


# Shuts down the bot (and all workers )
@bot.command(name="shutdown", aliases=["sh"])
@checks.is_owner()
async def shutdown(ctx):
    await ctx.send("Shutting down...")
    logger.log("SYSTEM", "------- SHUTTING DOWN --------------------")

    heartbeat.cancel()
    await bot.data_manager.data_shutdown()
    await bot.close()


# Hot-reload cogs command
@bot.command(name="reload", aliases=["rel"])
@checks.is_owner()
async def reload(ctx, cog: str):
    try:
        # Unload and load the cog asynchronously
        await bot.unload_extension(f'cogs.{cog}')
        await bot.load_extension(f'cogs.{cog}')
        
        await ctx.send(f"{emojis.mantis} Cog **{cog}** has been reloaded")
        logger.success(f"Reloaded cog: {cog}.py")
    except Exception as e:
        await ctx.send(f"❌ Error reloading cog **{cog}**: {e}")
        logger.error(f"Failed to reload {cog}.py: {e}")


# Sync slash commands
@bot.command(name="sync", aliases=["s"])
@checks.is_owner()
async def sync_commands(ctx):
    message = await ctx.send(f"{emojis.mantis} Syncing global tree...")
    try:
        await bot.wait_until_ready()
        synced = await bot.tree.sync()
        logger.success(f"{bot.user.name} has been synced globally, please wait for Discord's API to update")
    except Exception as e:
        await message.edit(content=f"❌ An error has occurred: {e}")
    else: 
        await message.edit(content=f"{emojis.mantis} Main tree globally synced {len(synced)} commands.") 


# Centralized prefix / hybrid error handling event
@bot.event
async def on_command_error(ctx, error):
    try:
        # Prevent a response if the user has no bot permissions
        def check_perms():
            guild_id = ctx.guild
            user = ctx.author
            channel = ctx.channel
            data_manager = bot.data_manager
            user_roles = user.roles

            search_access = [
                tup[1] for tup 
                in data_manager.access_roles
                if tup[0] == guild_id]

            if channel.permissions_for(user).administrator:
                return True

            for role in user_roles:
                if role.id in search_access:
                    return True
            return False
        
        if not check_perms():
            return

        errorMsg = "❌ An error occurred."
        
        if (ctx.author.id in owners):
                errorMsg = f"❌ An unexpected error occurred: {error}"

        if isinstance(error, commands.NotOwner):
            errorMsg = "❌ Ownership error: You need ownership of Mantid to use this command"

        elif isinstance(error, commands.MissingRequiredArgument):
            errorMsg = "❌ Command error: You are missing arguments"

        elif isinstance(error, commands.UserNotFound):
            errorMsg = "❌ Command error: Unable to find user"

        elif isinstance(error, commands.CommandNotFound):
            return
            errorMsg = "❌ This command does not exist, run /help to view available commands"
        
        elif isinstance(error, AccessError):
            errorMsg = f"❌ Access error: {error}"

        elif isinstance(error, BotError):

            if (ctx.author.id in owners):
                errorMsg = f"❌ An error occurred: {error}"
            logger.exception(f"❌ General command error: {error}")
        
        else:
            logger.error(f"❌ Command error: {error}")

        errorEmbed = discord.Embed(title="",
                                description=f"{errorMsg}",
                                color=0xFF0000)
        await ctx.send(embed=errorEmbed, ephemeral=True)

    except discord.errors.NotFound:
        logger.warning("Failed to send error message: Message context no longer exists")


# Centralized application error handling event
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    try:

        errorMsg = "❌ An error occurred."

        if interaction.user.id in owners:
            errorMsg = f"❌ An error occurred: {error}"

        if isinstance(error, app_commands.errors.MissingPermissions):
            errorMsg = "❌ You do not have the required permissions to use this command"

        elif isinstance(error, app_commands.errors.CommandNotFound):
            return
            errorMsg = "❌ This command does not exist, run /help to view available commands"

        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            errorMsg = f"❌ This command is on cooldown. Try again in {error.retry_after:.2f} seconds"

        elif isinstance(error, commands.NotOwner):
            errorMsg = "❌ Ownership error: You need ownership of Mantid to use this command"

        elif isinstance(error, AppAccessError):
            errorMsg = f"❌ Access error: {error}"

        elif isinstance(error, BotError):

            if interaction.user.id in owners:
                errorMsg = f"❌ An error occurred: {error}"
            logger.exception(f"❌ General command error: {error}")

        else:
            logger.error(f"❌ Unexpected command error: {error}")

        errorEmbed = discord.Embed(title="", description=errorMsg, color=0xFF0000)

        # Ensure the interaction is still valid before responding
        if interaction.response.is_done():
            await interaction.followup.send(embed=errorEmbed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)

    except discord.errors.NotFound:
        logger.warning("Failed to send error message: Interaction no longer exists.")

    except Exception as e:
        logger.error(f"Unexpected error in on_app_command_error: {e}")


bot.run(bot_token)
