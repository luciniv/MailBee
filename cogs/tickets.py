import discord
from discord.ext import commands
from discord import app_commands
from typing import List
from classes.error_handler import *
from classes.embeds import *
from utils import checks
from utils.logger import *


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


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
    async def status(self, ctx, status: discord.app_commands.Choice[str] = None, emoji: str = None):
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
        

    # Send a snip from the database
    @app_commands.command(name="set_type", description="Set the type of a tickets category")
    @checks.is_user_app()
    @app_commands.describe(category="Tickets category to set a type for")
    @app_commands.describe(type="Select a type, or search by keyword")
    async def set_type(self, interaction: discord.Interaction, category: discord.CategoryChannel, type: str):
        try:
            guild = interaction.guild
            types = [
                f"{typeID}: {name}" for typeID, name
                in self.bot.data_manager.types]
            
            typeEmbed = discord.Embed(title="", 
                                      description=f"Set **{category.name}** as type **{type}**", 
                                      color=0x3ad407)

            if type not in types:
                typeEmbed.description=f"❌ Type **{type}** not found"
                typeEmbed.color=0xFF0000
                await interaction.response.send_message(embed=typeEmbed)
                return
            
            typeID = int(type[:(type.index(":"))])

            search_monitor = [
                (channelID) for guildID, channelID, monitorType 
                in self.bot.data_manager.monitored_channels
                if (channelID == category.id)]
            
            if (len(search_monitor) == 0):
                typeEmbed.description=f"❌ Category is not a tickets category"
                typeEmbed.color=0xFF0000
                await interaction.response.send_message(embed=typeEmbed)
                return
            
            await self.bot.data_manager.set_type(guild.id, category.id, typeID)
            await interaction.response.send_message(embed=typeEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/set_type sent an error: {e}")


    @set_type.autocomplete('type')
    async def type_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return []
        
        types = [
            f"{typeID}: {name}" for typeID, name
            in self.bot.data_manager.types
            ]

        matches = [
            app_commands.Choice(name=type, value=type)
            for type in types
            if current.lower() in type.lower()]
        
        return matches[:25]
            
    
    

async def setup(bot):
    await bot.add_cog(Tickets(bot))
