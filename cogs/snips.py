import asyncio
import re
from typing import List

import discord
from discord import app_commands
from discord.app_commands import Range
from discord.ext import commands

from classes.error_handler import *
from classes.embeds import Embeds
from classes.helpers import *
from classes.paginator import *
from utils import checks
from utils.logger import *


class Snips(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_snip(self, ctx, snip: str, anon: bool = None):
        guild = ctx.guild
        channel = ctx.channel
        author = ctx.author
        thread_id, user_id = get_ticket_channel_info(channel)

        content = None
        snips = await self.bot.data_manager.get_or_load_snips(guild.id)

        for entry in snips:
            if snip.casefold() == entry["abbrev"]:
                content = entry["content"]

        if not content:
            return Embeds.error(
                description=f"❌ Snip **`{snip.casefold()}`** not found."
            )

        analytics = self.bot.get_cog("Analytics")
        if analytics:
            await ctx.message.delete()
            task = asyncio.create_task(
                analytics.route_to_dm(
                    content, channel, author, thread_id, user_id, anon
                )
            )
            result = await task
        return None

    def _format_snip_content(self, full_snip):
        return (
            full_snip["abbrev"],
            full_snip["summary"],
            full_snip["author_id"],
            full_snip["content"],
            full_snip["date"],
        )

    async def _load_snip_choices(
        self, guild: discord.Guild
    ) -> List[app_commands.Choice[str]]:
        if not guild:
            return []

        snips_raw = await self.bot.data_manager.get_or_load_snips(guild.id)
        snips = [f"{snip['abbrev']}: {snip['summary']}" for snip in snips_raw]
        choices = [app_commands.Choice(name=snip, value=snip) for snip in snips]

        return choices

    def _format_snip_embed(self, abbrev, summary, author_id, content, date):
        snip_embed = Embeds.success(title=f"Snip: {abbrev}", description=content)
        snip_embed.add_field(name="Summary", value=summary, inline=False)
        snip_embed.add_field(name="Author", value=f"<@{author_id}>", inline=False)
        snip_embed.add_field(
            name="Date", value=f"<t:{date}:D> (<t:{date}:R>)", inline=False
        )
        return snip_embed

    @commands.command(name="snip", aliases=["s"])
    @checks.is_ticket()
    @checks.is_user()
    @checks.is_guild()
    async def snip(self, ctx, *, snip: str):
        try:
            embed = await self._send_snip(ctx, snip, None)
            if embed:
                await ctx.channel.send(embed=embed)
                return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snip sent an error: {e}")

    @commands.command(name="asnip", aliases=["as"])
    @checks.is_ticket()
    @checks.is_user()
    @checks.is_guild()
    async def asnip(self, ctx, *, snip: str):
        try:
            embed = await self._send_snip(ctx, snip, True)
            if embed:
                await ctx.channel.send(embed=embed)
                return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+asnip sent an error: {e}")

    @commands.command(name="nonasnip", aliases=["nas"])
    @checks.is_ticket()
    @checks.is_user()
    @checks.is_guild()
    async def nonasnip(self, ctx, *, snip: str):
        try:
            embed = await self._send_snip(ctx, snip, False)
            if embed:
                await ctx.channel.send(embed=embed)
                return

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+nonasnip sent an error: {e}")

    @commands.command(name="snipview", aliases=["sv", "snip_view"])
    @checks.is_user()
    @checks.is_guild()
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
                await channel.send(
                    embed=Embeds.error(description=f"❌ Snip **`{abbrev}`** not found")
                )
                return

            abbrev, summary, author, content, date = self._format_snip_content(
                full_snip
            )
            snip_embed = self._format_snip_embed(abbrev, summary, author, content, date)
            await channel.send(embed=snip_embed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snipview sent an error: {e}")

    @commands.command(name="sniplist", aliases=["list", "sl"])
    @checks.is_user()
    @checks.is_guild()
    async def sniplist(self, ctx):
        try:
            pages = []
            guild = ctx.guild

            url = None
            if guild.icon:
                url = guild.icon.url

            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            if snips:
                if len(snips) == 0:
                    await ctx.send(
                        embed=Embeds.success(
                            title=f"Snip List", description="No snips found"
                        )
                    )
                    return
                else:
                    for i in range(0, len(snips), 6):
                        chunk = snips[i : i + 6]
                        snip_embed = Embeds.success(title=f"Snip List")
                        snip_embed.set_author(name=guild.name, icon_url=url)

                        for index, entry in enumerate(chunk, start=i + 1):
                            abbrev, summary, author, content, date = (
                                self._format_snip_content(entry)
                            )

                            if len(content) > 200:
                                content = content[:197] + "..."

                            snip_embed.add_field(
                                name=f"**Name:** {abbrev}",
                                value=f"**Summary:** {summary}\n"
                                f"**Content:** {content}\n"
                                f"**Author:** <@{author}>\n"
                                f"**Date:** <t:{date}:D> (<t:{date}:R>)\n{'⎯' * 20}",
                                inline=False,
                            )
                        pages.append(snip_embed)

            pages = add_footers(pages)
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            logger.exception(f"sniplist error: {e}")
            raise BotError(f"/sniplist sent an error: {e}")

    snip_group = app_commands.Group(name="snip", description="Manage snips")

    # Send a snip from the database
    @snip_group.command(name="send", description="Send a snip in a ticket")
    @checks.is_ticket_app()
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    @app_commands.describe(
        anon="Whether your message is anonymous or not (default is per server)"
    )
    async def send(
        self, interaction: discord.Interaction, snip: str, anon: bool = None
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            channel = interaction.channel
            author = interaction.user
            thread_id, user_id = get_ticket_channel_info(channel)

            content = ""
            guild = interaction.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            try:
                snip.index(":")
                abbrev = snip[: (snip.index(":"))]
            except Exception:
                abbrev = snip.casefold()

            for entry in snips:
                if abbrev.casefold() == entry["abbrev"]:
                    content = entry["content"]
                    break

            if not content:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"❌ Snip **`{abbrev}`** not found"),
                    ephemeral=True,
                )
                return

            analytics = self.bot.get_cog("Analytics")
            if analytics:
                task = asyncio.create_task(
                    analytics.route_to_dm(
                        content, channel, author, thread_id, user_id, anon
                    )
                )
                result = await task
                sentEmbed = Embeds.success(description="✅ Snip sent")
                await interaction.followup.send(embed=sentEmbed, ephemeral=True)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip send sent an error: {e}")

    @send.autocomplete("snip")
    async def snip_send_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_snip_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    # Send a snip for viewing
    @snip_group.command(name="view", description="View a snip")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(snip="Select a snip, or search by keyword")
    async def view(self, interaction: discord.Interaction, snip: str):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            full_snip = None
            try:
                snip.index(":")
                abbrev = snip[: (snip.index(":"))]
            except Exception:
                abbrev = snip.casefold()

            for entry in snips:
                if abbrev.casefold() == entry["abbrev"]:
                    full_snip = entry
                    break

            if not full_snip:
                await interaction.followup.send(
                    embed=Embeds.error(description=f"❌ Snip **`{abbrev}`** not found")
                )
                return

            abbrev, summary, author, content, date = self._format_snip_content(
                full_snip
            )
            snip_embed = self._format_snip_embed(abbrev, summary, author, content, date)
            await interaction.followup.send(embed=snip_embed)

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip view sent an error: {e}")

    @view.autocomplete("snip")
    async def snip_view_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_snip_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    # Add a snip to the database
    @snip_group.command(
        name="add", description="Create a snip, using inputted text or a message ID"
    )
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(abbreviation="Short-form name (alphanumeric only)")
    @app_commands.describe(summary="Summary of the snip's purpose")
    @app_commands.describe(content="Text content of the snip (4000 char max)")
    @app_commands.describe(message_id="ID of content message (4000 char max)")
    async def add(
        self,
        interaction: discord.Interaction,
        abbreviation: Range[str, 1, 20],
        summary: Range[str, 1, 80],
        content: str = None,
        message_id: str = None,
    ):
        try:
            await interaction.response.defer()

            message = None
            guild = interaction.guild
            channel = interaction.channel
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            abbrev = abbreviation.casefold()
            text = None

            if content is None and message_id is None:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ You must provide either the content or message_id fields"
                    )
                )
                return

            if not bool(re.fullmatch(r"[A-Za-z0-9 ]+", abbrev.casefold())):
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Snip abbreviations must be alphanumeric only"
                    )
                )
                return

            for snip in snips:
                if abbrev == snip["abbrev"]:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description=f"❌ **`{abbrev}`** already exists, remove this snip first"
                        )
                    )
                    return

            if content is None:
                message, response = await fetch_channel_message(channel, message_id)
                if not message:
                    await interaction.followup.send(
                        embed=Embeds.error(description=response)
                    )
                    return
                else:
                    text = message.content
            else:
                text = content

            content, response = await verify_text(self.bot, guild, text, 4000)
            if not content:
                await interaction.followup.send(
                    embed=Embeds.error(description=response)
                )
                return

            await self.bot.data_manager.add_snip(
                guild.id, interaction.user.id, abbrev.casefold(), text, summary
            )
            await self.bot.data_manager.get_or_load_snips(guild.id, False)
            await interaction.followup.send(
                embed=Embeds.success(
                    description=f"✅ Added snip **`{abbrev}`**\n**Content:**\n{text}"
                )
            )

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip add sent an error: {e}")

    # Delete a snip from the database
    @snip_group.command(name="remove", description="Remove a snip")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(snip="Select a snip to remove")
    async def remove(self, interaction: discord.Interaction, snip: str):
        try:
            await interaction.response.defer()
            guild = interaction.guild
            try:
                snip.index(":")
                abbrev = snip[: (snip.index(":"))]
            except Exception:
                await interaction.followup.send(
                    embed=Embeds.error(description="❌ Invalid snip selection")
                )
                return

            await self.bot.data_manager.remove_snip(guild.id, abbrev)
            await self.bot.data_manager.get_or_load_snips(guild.id, False)
            await interaction.followup.send(
                embed=Embeds.success(description=f"✅ Removed snip **`{abbrev}`**")
            )

        except Exception as e:
            logger.exception(e)
            raise BotError(f"/snip remove sent an error: {e}")

    @remove.autocomplete("snip")
    async def snip_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        guild = interaction.guild
        choices = await self._load_snip_choices(guild)

        matches = []

        for choice in choices:
            if current.casefold() in choice.name.casefold():
                matches.append(choice)

        return matches[:25]

    @commands.command(name="snips_export", description="Export all snips to a CSV file")
    @checks.is_user()
    @checks.is_guild()
    async def export_snips(self, ctx):
        try:
            guild = ctx.guild
            snips = await self.bot.data_manager.get_or_load_snips(guild.id)
            csv_data = "Abbreviation,Summary,Content\n"

            for snip in snips:
                csv_data += f"{snip['abbrev']},{snip['summary']},{snip['content']}\n"

            with open(f"{guild.id}_snips.csv", "w") as file:
                file.write(csv_data)

            await ctx.send(file=discord.File(f"{guild.id}_snips.csv"))

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snips_export sent an error: {e}")

    @commands.command(name="snips_import", description="Import snips from a CSV file")
    @checks.is_user()
    @checks.is_guild()
    async def import_snips(self, ctx, file: discord.Attachment):
        try:
            if not file.filename.endswith(".csv"):
                await ctx.send(
                    embed=Embeds.error(description="❌ Please upload a CSV file")
                )
                return

            csv_content = await file.read()
            lines = csv_content.decode().splitlines()
            guild = ctx.guild
            count = 0

            for line in lines[1:]:
                parts = line.split(",", 2)
                if len(parts) != 3:
                    continue

                abbrev, summary, content = parts
                abbrev = abbrev.strip().casefold()
                summary = summary.strip()
                content = content.strip()

                if not bool(re.fullmatch(r"[A-Za-z0-9 ]+", abbrev)):
                    continue

                if len(abbrev) < 1 or len(abbrev) > 20:
                    continue

                if len(summary) < 1 or len(summary) > 80:
                    continue

                if len(content) < 1 or len(content) > 4000:
                    continue

                snips = await self.bot.data_manager.get_or_load_snips(guild.id)
                exists = any(snip["abbrev"] == abbrev for snip in snips)
                if exists:
                    continue

                await self.bot.data_manager.add_snip(
                    guild.id, ctx.author.id, abbrev, content, summary
                )
                count += 1

            await self.bot.data_manager.get_or_load_snips(guild.id, False)
            await ctx.send(embed=Embeds.success(f"✅ Imported {count} snips"))

        except Exception as e:
            logger.exception(e)
            raise BotError(f"+snips_import sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Snips(bot))
