import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from classes.data_manager import DataManager
from classes.error_handler import *
from utils.channel_status import ChannelStatus
from utils import emojis, checks
from utils.logger import *


bot_token = os.getenv("BOT_TOKEN")
owners = list(map(int, os.getenv("OWNERS").split(",")))


startup = True
ready = True


# TODO
# ADD DATA ANALYSIS (PER SERVER, PER USER)
# ADD CSV WRITING

# LATER (QOL)
# CATEGORY OVERFLOW HANDLING
# TICKET STATUS LABELLING


class Mantid(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        description = ""

        # Create bot instance with command prefix
        super().__init__(command_prefix=commands.when_mentioned_or('m!'), intents=intents, description=description)
        self.data_manager = DataManager()
        self.channel_status = ChannelStatus()


    # Loads cogs when bot is ready
    async def on_ready(self):
        global ready
        global startup
        logger.log("SYSTEM", "------- STARTUP INITIATED ----------------")

        logger.log("SYSTEM", "------- FETCHING DATA --------------------")
        if startup and self.data_manager.db_pool is None:
            try:
                await self.data_manager.connect_to_db()
            except Exception as e:
                ready = False
                logger.critical(f"All database re-connect attempts failed: {e}")
                await self.close()
            if self.data_manager.db_pool is not None:
                await self.data_manager.update_cache()
                await self.data_manager.connect_to_redis()
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
                        logger.error(f"Failed to load {filename}: {e}")

        # Prints READY ASCII text, just looks weird here              
        if ready:
            logger.log("NOTIF", "\n  ___   ___     _     ___   __   __\n | _ \ | __|   /_\   |   \  \ \ / /\n |   / | _|   / _ \  | |) |  \ V / \n |_|_\ |___| /_/ \_\ |___/    |_|  \n")
            logger.log("SYSTEM", f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        else:
            logger.critical("❌❌❌ Bot experienced core failures: Resolve listed errors before further use ❌❌❌")
            self.close()


    # Close database and redis connections before shutdown
    async def on_close(self):
        logger.log("SYSTEM", "------- SHUTTING DOWN --------------------")
        await self.data_manager.close_db()
        await self.data_manager.close_redis()
        await super().close()


bot = Mantid()


# Hot-reload cogs command
@bot.command(name="reload", aliases=["r"])
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


# # Error handling for the reload command
# @reload.error
# async def reload_error(ctx, error):
#     if isinstance(error, commands.NotOwner):
#         logger.info(f"Denied !reload permissions for {ctx.message.author.name}")
#     else:
#         logger.error(f"!reload sent an error: {error}")


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


# # Error handling for the sync command
# @sync_commands.error
# async def sync_error(ctx, error):
#     if isinstance(error, commands.NotOwner):
#         logger.info(f"Denied !sync permissions for {ctx.message.author.name}")
#     else:
#         logger.error(f"!sync sent an error: {error}")


# Centralized error handling event
@bot.event
async def on_command_error(ctx, error):
    errorMsg = "❌ An unexpected error occurred. Please try again later"

    if isinstance(error, commands.NotOwner):
        errorMsg = f"❌ Ownership error: You need ownership of Mantid to use this command"
    
    elif isinstance(error, AccessError):
        errorMsg = f"❌ Access error: {error}"

    elif isinstance(error, BotError):
        if (ctx.author.id in owners):
            errorMsg = f"❌ An error occurred: {error}"
        else:
            errorMsg = f"❌ An error occurred"
        logger.error(f"❌ General command error: {error}")

    elif isinstance(error, commands.CommandNotFound):
        errorMsg = "❌ This command does not exist, run /help to view a list of available commands"
    
    else:
        logger.error(f"❌ Unexpected command error: {error}")

    errorEmbed = discord.Embed(title="",
                               description=f"{errorMsg}",
                               color=0xFF0000)
    await ctx.send(embed=errorEmbed, ephemeral=True)



# Run the bot
bot.run(bot_token)
