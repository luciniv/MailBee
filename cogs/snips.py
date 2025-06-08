import discord
from discord.ext import commands
from discord import app_commands
from typing import List
from classes.error_handler import *
from classes.embeds import *
from utils import checks
from utils.logger import *


class Snips(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # Send a snip from the database
    @app_commands.command(name="snip", description="Send a snip")
    @checks.is_user()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    @app_commands.describe(anon="Whether your message is anonymous or not (default is per server)")
    async def snip(self, interaction: discord.Interaction, snip: str, anon: bool = None):
        try:
            channel = interaction.channel
            author = interaction.user

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-3]

                    snip_content = ""
                    guild = interaction.guild
                    snips = [
                        f"{abbrev}: {summary}" for guildID, abbrev, summary 
                        in self.bot.data_manager.snip_list
                        if (guildID == guild.id)]
                    
                    snipEmbed = discord.Embed(title="", description="", color=discord.Color.green())

                    if snip not in snips:
                        snipEmbed.description=f"❌ Snip **`{snip}`** not found"
                        snipEmbed.color=discord.Color.red()
                        await interaction.response.send_message(embed=snipEmbed)
                        return
                    
                    abbrev = snip[:(snip.index(":"))]
                    
                    content = await self.bot.data_manager.get_snip(guild.id, abbrev)
                    if (len(content) != 0):
                        snip_content = content[0][0]

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await analytics.route_to_dm(snip_content, channel, author, threadID, userID, anon, True)
                        await interaction.response.send_message("Snip sent", ephemeral=True)
                    return

            errorEmbed = discord.Embed(title="", 
                                       description="❌ This command can only be used in ticket channels.",
                                       color=discord.Color.red())
            await interaction.response.send_message(embed=errorEmbed)
            
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
    

    # Send a snip from the database
    @app_commands.command(name="snip_view", description="View a snip")
    @checks.is_user()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    async def snip_view(self, interaction: discord.Interaction, snip: str):
        try:
            snip_content = ""
            guild = interaction.guild
            snips = [
                f"{abbrev}: {summary}" for guildID, abbrev, summary 
                in self.bot.data_manager.snip_list
                if (guildID == guild.id)]

            if snip not in snips:
                snipEmbed.description=f"❌ Snip **`{snip}`** not found"
                snipEmbed.color=discord.Color.red()
                await interaction.response.send_message(embed=snipEmbed)
                return
            
            abbrev = snip[:(snip.index(":"))]
            summary = snip[(snip.index(":") + 1):]
            
            content = await self.bot.data_manager.get_snip(guild.id, abbrev)
            if (len(content) != 0):
                snip_content = content[0][0]

            snipEmbed = discord.Embed(title=abbrev, description="", 
                                      color=discord.Color.green())
            snipEmbed.add_field(name="Summary", value=summary, inline=False)
            snipEmbed.add_field(name="Content", value=snip_content, inline=False)

            await interaction.response.send_message(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip sent an error: {e}")


    @snip_view.autocomplete('snip')
    async def snip_view_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

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
    @checks.is_user()
    @app_commands.describe(abbreviation="Short-form name for the snip (24 char max)")
    @app_commands.describe(summary="Summary of the snip's purpose (100 char max)")
    @app_commands.describe(message_id="ID of the message to use as the snip (3000 char max)")
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
                                    color=discord.Color.green())

            if (len(snips) != 0):
                snipEmbed.description=f"❌ **`{abbreviation.lower()}`** already exists, remove or edit this snip instead"
                snipEmbed.color=discord.Color.red()
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            if (len(abbreviation) > 24):
                snipEmbed.description="❌ Your abbreviation is too many characters long (max is 24)"
                snipEmbed.color=discord.Color.red()
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            if (len(summary) > 100):
                snipEmbed.description="❌ Your summary is too many characters long (max is 100)"
                snipEmbed.color=discord.Color.red()
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
                snipEmbed.color=discord.Color.red()
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return

            if (message is None):
                snipEmbed.description="❌ Message not found, try re-entering the ID"
                snipEmbed.color=discord.Color.red()
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            
            if (len(message.content) > 3000):
                snipEmbed.description=("❌ Your snip message is too many characters long (max is 3000). "
                                       "Note that channel links add around 70 characters.")
                snipEmbed.color=discord.Color.red()
                await interaction.followup.send(embed=snipEmbed, ephemeral=True)
                return
            
            text = await self.bot.helper.convert_mentions(message.content, guild)

            await self.bot.data_manager.add_snip(guild.id, interaction.user.id, abbreviation.lower(), summary, text)
            await interaction.followup.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip_add sent an error: {e}")


    # Delete a snip from the database
    @app_commands.command(name="snip_remove", description="Remove a snip")
    @checks.is_user()
    @app_commands.describe(snip="Select a snip to remove")
    async def snip_remove(self, interaction: discord.Interaction, snip: str):
        try:
            guild = interaction.guild
            snips = [
                f"{abbrev}: {summary}" for guildID, abbrev, summary 
                in self.bot.data_manager.snip_list
                if (guildID == guild.id)]
            
            snipEmbed = discord.Embed(title="", description="", color=discord.Color.green())
            
            if snip not in snips:
                snipEmbed.description=f"❌ Snip **`{snip}`** not found"
                snipEmbed.color=discord.Color.red()
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

async def setup(bot):
    await bot.add_cog(Snips(bot))