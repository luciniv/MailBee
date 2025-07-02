import discord
import re
import asyncio
from discord.ext import commands
from discord import app_commands
from discord.app_commands import Range
from typing import List
from classes.error_handler import *
from classes.paginator import *
from classes.embeds import *
from utils import checks
from utils.logger import *


class Snips(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="snip", aliases=["s"])
    @checks.is_guild()
    @checks.is_user()
    async def snip(self, ctx, *, snip: str):
        try:
            channel = ctx.channel
            author = ctx.author

            errorEmbed = discord.Embed(description=f"❌ Snip **`{snip.casefold()}`** not found",
                                           color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    content = None
                    guild = ctx.guild
                    snips = await self.bot.data_manager.get_or_load_snips(guild.id)

                    for entry in snips:
                        if snip.casefold() == entry["abbrev"]:
                            content = entry["content"]

                    if content is None:
                        await channel.send(embed=errorEmbed)
                        return

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await ctx.message.delete()
                        task = asyncio.create_task(analytics.route_to_dm(content, channel, author, threadID, userID, None, True))
                        result = await task
                    return
    
            errorEmbed.description="❌ This command can only be used in ticket channels."
            await channel.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snip sent an error: {e}")
        

    @commands.command(name="asnip", aliases=["as"])
    @checks.is_guild()
    @checks.is_user()
    async def asnip(self, ctx, *, snip: str):
        try:
            channel = ctx.channel
            author = ctx.author

            errorEmbed = discord.Embed(description=f"❌ Snip **`{snip.casefold()}`** not found",
                                           color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    content = None
                    guild = ctx.guild
                    snips = await self.bot.data_manager.get_or_load_snips(guild.id)

                    for entry in snips:
                        if snip.casefold() == entry["abbrev"]:
                            content = entry["content"]

                    if content is None:
                        await channel.send(embed=errorEmbed)
                        return

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await ctx.message.delete()
                        task = asyncio.create_task(analytics.route_to_dm(content, channel, author, threadID, userID, True, True))
                        result = await task
                    return
      
            errorEmbed.description="❌ This command can only be used in ticket channels."
            await channel.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+asnip sent an error: {e}")
        

    @commands.command(name="nonasnip", aliases=["nas"])
    @checks.is_guild()
    @checks.is_user()
    async def nonasnip(self, ctx, *, snip: str):
        try:
            channel = ctx.channel
            author = ctx.author

            errorEmbed = discord.Embed(description=f"❌ Snip **`{snip.casefold()}`** not found",
                                           color=discord.Color.red())

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    content = None
                    guild = ctx.guild
                    snips = await self.bot.data_manager.get_or_load_snips(guild.id)

                    for entry in snips:
                        if snip.casefold() == entry["abbrev"]:
                            content = entry["content"]

                    if content is None:
                        await channel.send(embed=errorEmbed)
                        return

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        await ctx.message.delete()
                        task = asyncio.create_task(analytics.route_to_dm(content, channel, author, threadID, userID, False, True))
                        result = await task
                    return
       
            errorEmbed.description="❌ This command can only be used in ticket channels."
            await channel.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"+nonasnip sent an error: {e}")
        

    @commands.command(name="snipview", description="List all current snips",
                             aliases=["sv", "snip_view"])
    @checks.is_guild()
    @checks.is_user()
    async def snipview(self, ctx, *, snip: str):   
        try:
            channel = ctx.channel
            guild = ctx.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            full_snip = None

            abbrev = snip.casefold()

            for entry in snips:
                if abbrev == entry["abbrev"]:
                    full_snip = entry

            if full_snip is None:
                errorEmbed = discord.Embed(description=f"❌ Snip **`{abbrev}`** not found",
                                           color=discord.Color.red())
                await channel.send(embed=errorEmbed)
                return

            summary = full_snip["summary"]
            author = full_snip["authorID"]
            content = full_snip["content"]
            date = full_snip["date"]

            snipEmbed = discord.Embed(title=f"Snip: {abbrev}", description=content, 
                                      color=discord.Color.green())
            snipEmbed.add_field(name="Summary", value=summary, inline=False)
            snipEmbed.add_field(name="Author", value=f"<@{author}>", inline=False)
            snipEmbed.add_field(name="Date", value=f"<t:{date}:D> (<t:{date}:R>)", inline=False)

            await channel.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snipview sent an error: {e}")
        

    @commands.hybrid_command(name="sniplist", description="List all current snips",
                             aliases=["list", "sl"])
    @checks.is_guild()
    @checks.is_user()
    async def sniplist(self, ctx):     
        try:
            pages = []
            count = 0
            limit = 0
            guild = ctx.guild

            snipEmbed = discord.Embed(title=f"Snip List",
                                  description="No snips found",
                                  color=discord.Color.green())
            url = None
            if (guild.icon):
                url = guild.icon.url
            snipEmbed.set_author(name=guild.name, icon_url=url)

            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            if snips is not None:
                if len(snips) == 0:
                    await ctx.send(embed=snipEmbed)
                    return
                else:
                    page_counts = build_subsections(len(snips), 6)
                    for page_count in page_counts:
                        limit += page_count
                        snipEmbed = discord.Embed(title=f"Snip List",
                                description="",
                                color=discord.Color.green())
                        snipEmbed.set_author(name=guild.name, icon_url=url)

                        while (count < limit):
                            entry = snips[count]

                            abbrev = entry["abbrev"]
                            summary = entry["summary"]
                            authorID = entry["authorID"]
                            content = entry["content"]
                            date = entry["date"]

                            if len(content) > 200:
                                content = content[:197] + "..."

                            snipEmbed.add_field(name=f"**Name:** {abbrev}", 
                                            value=f"**Summary:** {summary}\n"
                                            f"**Content:** {content}\n"
                                            f"**Author:** <@{authorID}>\n"
                                            f"**Date:** <t:{date}:D> (<t:{date}:R>)\n{'⎯' * 20}",
                                            inline=False)
                            count += 1
                        pages.append(snipEmbed)

            for page in range(len(pages)):
                pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            logger.exception(f"sniplist error: {e}")
            raise BotError(f"/sniplist sent an error: {e}")
        

    snip_group = app_commands.Group(name="snip", description="Manage snips")


    # Send a snip from the database
    @snip_group.command(name="send", description="Send a snip in a ticket")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    @app_commands.describe(anon="Whether your message is anonymous or not (default is per server)")
    async def send(self, interaction: discord.Interaction, snip: str, anon: bool = None):
        try:
            await interaction.response.defer()

            channel = interaction.channel
            author = interaction.user

            if (channel.topic):
                if ("Ticket channel" in channel.topic):
                    id_list = (channel.topic).split()
                    threadID = id_list[-1]
                    userID = id_list[-2]

                    content = ""
                    guild = interaction.guild
                    snips = await self.bot.data_manager.get_or_load_snips(guild.id)

                    abbrev = snip[:(snip.index(":"))]

                    for entry in snips:
                        if abbrev.casefold() == entry["abbrev"]:
                            content = entry["content"]

                    analytics = self.bot.get_cog("Analytics")
                    if analytics is not None:
                        task = asyncio.create_task(analytics.route_to_dm(content, channel, author, threadID, userID, anon, True))
                        result = await task
                        sentEmbed=discord.Embed(description="✅ Snip sent", color=discord.Color.green())
                        await interaction.followup.send(embed=sentEmbed, ephemeral=True)
                    return
   
            errorEmbed = discord.Embed(description="❌ This command can only be used in ticket channels.",
                                        color=discord.Color.red())
            await interaction.followup.send(embed=errorEmbed)
            
        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip send sent an error: {e}")


    @send.autocomplete('snip')
    async def snip_send_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get snips for the specific guild
        snips_raw = await self.bot.data_manager.get_or_load_snips(guild.id)

        snips = [
                f"{snip['abbrev']}: {snip['summary']}" 
                for snip in snips_raw]

        matches = [
            app_commands.Choice(name=snip, value=snip)
            for snip in snips
            if current.casefold() in snip.casefold()]
        
        return matches[:25]
    

    # Send a snip for viewing
    @snip_group.command(name="view", description="View a snip")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    async def view(self, interaction: discord.Interaction, snip: str):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            full_snip = None

            abbrev = snip[:(snip.index(":"))]

            for entry in snips:
                if abbrev.casefold() == entry["abbrev"]:
                    full_snip = entry

            summary = full_snip["summary"]
            author = full_snip["authorID"]
            content = full_snip["content"]
            date = full_snip["date"]

            snipEmbed = discord.Embed(title=f"Snip: {abbrev}", description=content, 
                                      color=discord.Color.green())
            snipEmbed.add_field(name="Summary", value=summary, inline=False)
            snipEmbed.add_field(name="Author", value=f"<@{author}>", inline=False)
            snipEmbed.add_field(name="Date", value=f"<t:{date}:D> (<t:{date}:R>)", inline=False)

            await interaction.followup.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip view sent an error: {e}")


    @view.autocomplete('snip')
    async def snip_view_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get snips for the specific guild
        snips_raw = await self.bot.data_manager.get_or_load_snips(guild.id)

        snips = [
                f"{snip['abbrev']}: {snip['summary']}" 
                for snip in snips_raw]

        matches = [
            app_commands.Choice(name=snip, value=snip)
            for snip in snips
            if current.casefold() in snip.casefold()]
        
        return matches[:25]


    # Add a snip to the database
    @snip_group.command(name="add", description="Create a snip, using inputted text or a message ID")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(abbreviation="Short-form name for the snip (alphanumeric only)")
    @app_commands.describe(summary="Summary of the snip's purpose")
    @app_commands.describe(content="Text content of the snip (LEAVE BLANK IF USING A MESSAGE ID)")
    @app_commands.describe(message_id="ID of the message to use as the snip (4000 char max)")
    async def add(self, interaction: discord.Interaction, abbreviation: Range[str, 1, 20], summary: Range[str, 1, 80], 
                       content: str = None, message_id: str = None):
        try:
            await interaction.response.defer()
            message = None
            guild = interaction.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            abbrev = abbreviation.casefold()
            text = None
            
            errorEmbed = discord.Embed(description="❌ You must provide either the content or message_id fields",
                                       color=discord.Color.red())
            
            if content is None and message_id is None:
                await interaction.followup.send(embed=errorEmbed)
                return
                
            
            if not bool(re.fullmatch(r"[A-Za-z0-9 ]+", abbrev.casefold())):
                errorEmbed.description="❌ Snip abbreviations must be alphanumeric only"
                await interaction.followup.send(embed=errorEmbed)
                return
            
            for snip in snips:
                if abbrev == snip["abbrev"]:
                    errorEmbed.description=(f"❌ **`{abbrev}`** already exists, remove this snip first")
                    await interaction.followup.send(embed=errorEmbed)
                    return
                
            if content is None:
                try:
                    message = await interaction.channel.fetch_message(int(message_id))
                except discord.NotFound:
                    errorEmbed.description="❌ Message ID must be from a valid message in the current channel",
                    await interaction.followup.send(embed=errorEmbed)
                    return
                
                except discord.HTTPException:
                    errorEmbed.description="❌ Message not found, try re-entering the ID"
                    await interaction.followup.send(embed=errorEmbed)
                    return

                if (message is None):
                    errorEmbed.description="❌ Message not found, try re-entering the ID"
                    await interaction.followup.send(embed=errorEmbed)
                    return
                
                if len(message.content) < 1:
                    errorEmbed.description="❌ Message is too short"
                    await interaction.followup.send(embed=errorEmbed)
                    return
                
                text = message.content
            else:
                text = content

            text = await self.bot.helper.convert_mentions(text, guild)

            if (len(text) > 4000):
                errorEmbed.description=("❌ Your snip message is too many characters long (max is 4000). "
                                        "Note that channel links add around 70 characters.")
                await interaction.followup.send(embed=errorEmbed)
                return

            snipEmbed = discord.Embed(description=f"✅ Added snip **`{abbrev}`**\n**Content:**\n{text}",
                                    color=discord.Color.green())

            await self.bot.data_manager.add_snip(guild.id, interaction.user.id, abbrev.casefold(), text, summary)
            await self.bot.data_manager.get_or_load_snips(guild.id, False)
            await interaction.followup.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip add sent an error: {e}")


    # Delete a snip from the database
    @snip_group.command(name="remove", description="Remove a snip")
    @checks.is_guild()
    @checks.is_user()
    @app_commands.describe(snip="Select a snip to remove")
    async def remove(self, interaction: discord.Interaction, snip: str):
        try:
            await interaction.response.defer()
            guild = interaction.guild
           
            abbrev = snip[:(snip.index(":"))]
            
            snipEmbed = discord.Embed(description=f"✅ Removed snip **`{abbrev}`**", 
                                      color=discord.Color.green())

            await self.bot.data_manager.remove_snip(guild.id, abbrev)
            await self.bot.data_manager.get_or_load_snips(guild.id, False)
            await interaction.followup.send(embed=snipEmbed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip remove sent an error: {e}")


    @remove.autocomplete('snip')
    async def snip_remove_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        if not guild:
            return [] 

        # Get snips for the specific guild
        snips_raw = await self.bot.data_manager.get_or_load_snips(guild.id)

        snips = [
                f"{snip['abbrev']}: {snip['summary']}" 
                for snip in snips_raw]

        matches = [
            app_commands.Choice(name=snip, value=snip)
            for snip in snips
            if current.casefold() in snip.casefold()]
        
        return matches[:25]
    

async def setup(bot):
    await bot.add_cog(Snips(bot))