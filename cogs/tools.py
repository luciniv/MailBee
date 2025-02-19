import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import List
from classes.error_handler import *
from classes.embeds import *
from utils import checks
from utils.logger import *


class Tools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # Send a snip from the database
    @app_commands.command(name="snip", description="Send a snip")
    @checks.is_user_app()
    @app_commands.describe(snip="Selected snip")
    async def snip(self, interaction: discord.Interaction, snip: str):
        try:
            snip_content = ""
            guild = interaction.guild
            snips = [
                f"{abbrev}: {summary}" for guildID, abbrev, summary 
                in self.bot.data_manager.snip_list
                if (guildID == guild.id)]
            
            snipEmbed = discord.Embed(title="", description="", color=0x3ad407)

            if snip not in snips:
                snipEmbed.description=f"❌ Snip **`{snip}`** not found"
                snipEmbed.color=0xFF0000
                await interaction.response.send_message(embed=snipEmbed)
                return
            
            abbrev = snip[:(snip.index(":"))]
            
            content = await self.bot.data_manager.get_snip(guild.id, abbrev)
            if (len(content) != 0):
                snip_content = content[0][0]
            await interaction.response.send_message(snip_content)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip sent an error: {e}")


    @snip.autocomplete('snip')
    async def snip_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get snips for the specific guild
        snips = [
            f"{abbrev}: {summary}" for guildID, abbrev, summary 
            in self.bot.data_manager.snip_list 
            if (guildID == guild.id)]

        matches = [
            app_commands.Choice(name=snip, value=snip)
            for snip in snips
            if current.lower() in snip.lower()]
        
        return matches[:25]


    # Add a snip to the database
    @app_commands.command(name="snip_add", description="Use the ID of a message to create a snip with its contents")
    @checks.is_user_app()
    @app_commands.describe(abbreviation="Short-form name for the snip (24 char max)")
    @app_commands.describe(summary="Summary of the snip's purpose (100 char max)")
    @app_commands.describe(message_id="ID of the message to use as the snip (1800 char max)")
    async def snip_add(self, interaction: discord.Interaction, abbreviation: str, summary: str, message_id: str):
        try:
            await interaction.response.defer()
            message = None
            guild = interaction.guild
            snips = [
                abbrev for guildID, abbrev, summary 
                in self.bot.data_manager.snip_list
                if ((guildID == guild.id) and (abbrev == abbreviation.lower()))]

            snipEmbed = discord.Embed(title="",
                                    description=f"✅ Added snip **`{abbreviation.lower()}`**",
                                    color=0x3ad407)

            if (len(snips) != 0):
                snipEmbed.description=f"❌ **`{abbreviation.lower()}`** already exists, remove or edit this snip instead"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            if (len(abbreviation) > 24):
                snipEmbed.description="❌ Your abbreviation is too many characters long (max is 24)"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            if (len(summary) > 100):
                snipEmbed.description="❌ Your summary is too many characters long (max is 100)"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            
            try:
                message = await interaction.channel.fetch_message(int(message_id))
            except discord.NotFound:
                
                # Check all channels if message wasnt in the first
                for channel in interaction.guild.text_channels:
                    try:
                        message = await channel.fetch_message(int(message_id))  
                    except discord.NotFound:
                        continue 
                    except discord.HTTPException:
                        continue 

            except discord.HTTPException:
                snipEmbed.description="❌ Message not found, try re-entering the ID"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return

            if (message is None):
                snipEmbed.description="❌ Message not found, try re-entering the ID"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            
            if (len(message.content) > 1800):
                snipEmbed.description="❌ Your snip message is too many characters long (max is 1800)"
                snipEmbed.color=0xFF0000
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return

            await self.bot.data_manager.add_snip(guild.id, interaction.user.id, abbreviation.lower(), summary, message.content)
            await interaction.followup.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip_add sent an error: {e}")


    # Delete a snip from the database
    @app_commands.command(name="snip_remove", description="Remove a snip")
    @checks.is_user_app()
    @app_commands.describe(snip="Selected snip to remove")
    async def snip_remove(self, interaction: discord.Interaction, snip: str):
        try:
            guild = interaction.guild
            snips = [
                f"{abbrev}: {summary}" for guildID, abbrev, summary 
                in self.bot.data_manager.snip_list
                if (guildID == guild.id)]
            
            snipEmbed = discord.Embed(title="", description="", color=0x3ad407)
            
            if snip not in snips:
                snipEmbed.description=f"❌ Snip **`{snip}`** not found"
                snipEmbed.color=0xFF0000
                await interaction.response.send_message(embed=snipEmbed)
                return
            
            abbrev = snip[:(snip.index(":"))]
            
            snipEmbed.description=f"✅ Removed snip **`{abbrev}`**"

            await self.bot.data_manager.remove_snip(guild.id, abbrev)
            await interaction.response.send_message(embed=snipEmbed)
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip_remove sent an error: {e}")


    @snip_remove.autocomplete('snip')
    async def snip_remove_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get snips for the specific guild
        snips = [
            f"{abbrev}: {summary}" for guildID, abbrev, summary 
            in self.bot.data_manager.snip_list 
            if (guildID == guild.id)]

        matches = [
            app_commands.Choice(name=snip, value=snip)
            for snip in snips
            if current.lower() in snip.lower()]
        
        return matches[:25]


    # Manually update the status of a ticket channel
    @commands.hybrid_command(name="status", description="Change the emoji status of a ticket")
    @checks.is_user()
    @app_commands.describe(status="Select an emoji from the defined list, or add a custom one" 
                                    " (unicode only)")
    @app_commands.choices(status=[
        app_commands.Choice(name=f"🆕 - new ticket", value="new"),
        app_commands.Choice(name=f"❗️ - pending moderator response", value="alert"),
        app_commands.Choice(name=f"⏳ - waiting for user response", value="wait")])
    @app_commands.describe(emoji="Enter a default Discord emoji (only works without status choice)")
    async def show(self, ctx, status: discord.app_commands.Choice[str] = None, emoji: str = None):
        try:    
            status_flag = False
            channel = ctx.channel
            emoji_name = None
            emoji_str = None

            if status is None and emoji is None:
                errorEmbed = discord.Embed(title=f"", 
                                    description="❌ You must select a status or provide an emoji", 
                                    color=0xFF0000)

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

            result = await self.bot.channel_status.set_emoji(channel, emoji_str, True)

            # Fix for outputting readable explanation of what the emoji is for
            if status_flag:
                emoji_str = emoji_name

            statusEmbed = Embeds(self.bot, title="", 
                                description=f"Channel status set to {emoji_str}\n*Please wait up to 5 minutes for edits to appear*")

            if not result:
                statusEmbed.description=f"Failed to set channel status to {emoji_str}, current or pending status is already set as this"
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
