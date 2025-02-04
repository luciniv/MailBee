import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from classes.error_handler import *
from utils import emojis, checks
from utils.logger import *


class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # Manually update the status of a ticket channel
    @commands.hybrid_command(name="status", description="Change the emoji status of a ticket")
    @checks.has_access()
    @app_commands.describe(status="Select an emoji from the defined list, or add a custom one" 
                                    " (Mantid only supports unicode emojis)")
    @app_commands.choices(status=[
        app_commands.Choice(name=f"🆕 - new ticket", value="new"),
        app_commands.Choice(name=f"❗️ - pending moderator response", value="alert"),
        app_commands.Choice(name=f"⏳ - waiting for user response", value="wait")])
    @app_commands.describe(emoji="Enter a default Discord emoji (only applied if you did not select an emoji from the status options)")
    async def show(self, ctx, status: discord.app_commands.Choice[str] = None, emoji: str = None):
        try:    
            status_flag = False
            channel = ctx.channel
            bot_user = self.bot.user
            emoji_name = None
            emoji_str = None

            if status is None and emoji is None:
                errorEmbed = discord.Embed(title=f"", 
                                        description="❌ You must select a status or provide an emoji", 
                                        color=0xFF0000)
                errorEmbed.timestamp = datetime.now(timezone.utc)
                errorEmbed.set_footer(text="Mantid", icon_url=bot_user.avatar.url)

                await ctx.send(embed=errorEmbed, ephemeral=True)
                return

            # Prioritizes status selection over custom emojis
            if status is not None:
                status_flag = True
                emoji_name = status.name
                emoji_str = status.value

            if emoji_str is None:
                if (self.bot.channel_status.check_unicode(emoji)):
                    emoji_str = emoji

            result = await self.bot.channel_status.set_emoji(channel, emoji_str)

            # Fix for outputting readable explanation of what the emoji is for
            if status_flag:
                emoji_str = emoji_name

            statusEmbed = discord.Embed(title="", 
                                    description=f"Channel status set to {emoji_str}\n\n*Please wait up to 5 minutes for edits to appear*", 
                                    color=0x3ad407)
            statusEmbed.timestamp = datetime.now(timezone.utc)
            statusEmbed.set_footer(text="Mantid", icon_url=bot_user.avatar.url)

            if not result:
                statusEmbed.description=f"Failed to set channel status to {emoji_str}, did you try to set a 🆕 status to ❗️?"
                statusEmbed.color=0xFF0000

            await ctx.reply(embed=statusEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/status sent an error: {e}")


    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if (isinstance(channel, discord.TextChannel)):
            guild = channel.guild
            category = channel.category
            new_category = None
            overflow_cats = []

            # Gets all monitored channels / categories for the guild
            search_monitor = [
                (channelID) for guildID, channelID, monitorType 
                in self.bot.data_manager.monitored_channels
                if (guildID == guild.id)]
            
            # Guild has no monitored channels
            if (len(search_monitor) == 0):
                return 
            
            # Category is monitored
            if category.id in search_monitor:
                for cat_channel in category.channels:

                    # Category contains modmail channel
                    if cat_channel.id in search_monitor:
                        if (len(category.channels) >= 45):
                            
                            # Scan for pre-exisitng non-full overflow categories
                            categories = guild.categories
                            for cat in categories:
                                if (((cat.name).split())[0] == "Overflow"):
                                    overflow_cats.append(cat)
        
                            # Create OVERFLOW 1 category after MODMAIL, move channel there
                            if (len(overflow_cats) == 0):
                                index = guild.categories.index(category) + 1
                                new_category = await guild.create_category(name="Overflow 1", 
                                                                        overwrites=category.overwrites,
                                                                        position=index)
                                await channel.edit(category=new_category)
                                await self.bot.data_manager.add_monitor(guild.id, new_category.id, "Overflow category")
                                return      
                    
                            else:
                                cat_id = 1
                                for cat in overflow_cats:
                                    if (cat_id == int(((cat.name).split())[1])):
                                        # if category has space, insert
                                        if (len(cat.channels) < 50):
                                            await channel.edit(category=cat)
                                            return
                                        else:
                                            cat_id += 1
                                    else:
                                        # create new category, since there was a gap
                                        index = guild.categories.index(cat) - 1
                                        new_category = await guild.create_category(name=f"Overflow {cat_id}", 
                                                                            overwrites=category.overwrites,
                                                                            position=index)
                                        await channel.edit(category=new_category)
                                        await self.bot.data_manager.add_monitor(guild.id, new_category.id, "Overflow category")
                                        return
                                    
                                # create new category, since there were no open categories
                                index = guild.categories.index(overflow_cats[-1]) + 1
                                new_category = await guild.create_category(name=f"Overflow {cat_id}", 
                                                                        overwrites=category.overwrites,
                                                                        position=index)
                                await channel.edit(category=new_category)
                                await self.bot.data_manager.add_monitor(guild.id, new_category.id, "Overflow category")

                        else:
                            # modmail cat isnt full yet
                            return
                    
                        
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if (isinstance(channel, discord.CategoryChannel)):
            guild = channel.guild
            search_monitor = [
                (channelID) for guildID, channelID, monitorType 
                in self.bot.data_manager.monitored_channels
                if (channelID == channel.id)]
            
            if (len(search_monitor) != 0):
                await self.bot.data_manager.remove_monitor(channel.id)
                print(f"removed {channel.name} from monitor")

async def setup(bot):
    await bot.add_cog(Tools(bot))
