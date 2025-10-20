import asyncio
import datetime
import re

import discord
from discord import app_commands
from discord.ext import commands

from classes.embeds import Embeds
from classes.error_handler import *
from classes.helpers import *
from classes.paginator import Paginator
from utils import checks, emojis
from utils.logger import *


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ticket_history", aliases=["tickets", "history", "th"])
    @checks.is_user()
    @checks.is_guild()
    async def ticket_history(self, ctx, user: discord.Member):
        try:
            pages = []

            history = await self.bot.data_manager.get_ticket_history(
                ctx.guild.id, user.id
            )
            if history is not None:
                if len(history) == 0:
                    historyEmbed = Embeds.success(
                        title="Ticket History",
                        description="User has not opened any tickets",
                    )
                    historyEmbed.set_author(
                        name=f"{user.name} | {user.id}",
                        icon_url=user.display_avatar.url,
                    )
                    await ctx.send(embed=historyEmbed)
                    return
                else:
                    for i in range(0, len(history), 5):
                        chunk = history[i : i + 5]
                        historyEmbed = Embeds.success(
                            title="Ticket History",
                            description="Tickets are displayed by most recent open date.\n"
                            "Logs may appear as `#unknown` before being accessed.",
                        )

                        historyEmbed.set_author(
                            name=f"{user.name} | {user.id}",
                            icon_url=(user.avatar and user.avatar.url)
                            or user.display_avatar.url,
                        )

                        for index, ticket in enumerate(chunk, start=i + 1):
                            ticket_id = ticket[0]
                            log_id = ticket[1]
                            date_open = int(ticket[2].timestamp())
                            date_close = None
                            close = ticket[3]
                            if close is not None:
                                date_close = f"<t:{int(close.timestamp())}:D>"
                            close_id = ticket[4]
                            if close_id is not None:
                                close_id = f"<@{close_id}>"
                            state = (ticket[5]).upper()
                            typeName = ticket[6]

                            historyEmbed.add_field(
                                name=f"{index}) {typeName} Ticket: {state}",
                                value=f"`ID: {ticket_id}`\n**Opened:** <t:{date_open}:D>\n**Closed:** {date_close}\n"
                                f"**Closed By:** {close_id}\n**Logs:** <#{log_id}>\n{'⎯' * 20}",
                                inline=False,
                            )
                        pages.append(historyEmbed)

            pages = add_footers(pages)
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/ticket_history sent an error: {e}")

    # TODO: Prefix note commands

    note_group = app_commands.Group(name="note", description="Manage notes")

    @note_group.command(name="add_ticket", description="Add a note to a ticket")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(note="Content of the note")
    @app_commands.describe(ticket_id="Ticket ID to add a note to")
    async def add_ticket(
        self, interaction: discord.Interaction, note: str, ticket_id: int
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            mod = interaction.user
            state, content = await verify_text(self.bot, guild, note)

            if state:
                ticket_exists, opener_id, log_id = (
                    await self.bot.data_manager.check_ticket_exists(guild.id, ticket_id)
                )
                if ticket_exists:
                    note_id = await self.bot.data_manager.get_next_note_id(guild.id)
                    await self.bot.data_manager.add_note(
                        note_id,
                        guild.id,
                        opener_id,
                        ticket_id,
                        log_id,
                        mod.id,
                        mod.name,
                        content,
                    )
                    await interaction.followup.send(
                        embed=Embeds.success(
                            description=(
                                f"✅ Note added for ticket: **{ticket_id}**"
                                f"\n**Content:** {content}"
                            )
                        )
                    )
                else:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ No ticket found with that ID."
                        )
                    )
            else:
                await interaction.follow.send(embed=Embeds.error(description=content))

        except Exception as e:
            raise BotError(f"/note add_ticket sent an error: {e}")

    @note_group.command(name="add_user", description="Add a note to a user")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(note="Content of the note")
    @app_commands.describe(user="User to add the note to")
    async def add_user(
        self, interaction: discord.Interaction, note: str, user: discord.Member
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            mod = interaction.user
            state, content = await verify_text(self.bot, guild, note)

            if state:
                note_id = await self.bot.data_manager.get_next_note_id(guild.id)
                await self.bot.data_manager.add_note(
                    note_id,
                    guild.id,
                    user.id,
                    -1,
                    -1,
                    mod.id,
                    mod.name,
                    content,
                )
                await interaction.followup.send(
                    embed=Embeds.success(
                        description=(
                            f"✅ Note added for user: **{user.name}** ({user.id})"
                            f"\n**Content:** {content}"
                        )
                    )
                )
            else:
                await interaction.follow.send(embed=Embeds.error(description=content))

        except Exception as e:
            raise BotError(f"/note add_user sent an error: {e}")

    @note_group.command(name="view", description="View note(s) from a ticket or user")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(ticket_id="Ticket ID to view noted from")
    @app_commands.describe(user="User to view notes from")
    async def view(
        self,
        interaction: discord.Interaction,
        ticket_id: int = None,
        user: discord.Member = None,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild

            if not ticket_id and not user:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Must provide either ticket_id or user."
                    )
                )
                return

            elif ticket_id and user:
                await interaction.followup.send(
                    embed=Embeds.error(
                        description="❌ Must provide only one of ticket_id or user."
                    )
                )
                return

            notes = []
            if ticket_id:
                ticket_exists, _, _ = await self.bot.data_manager.check_ticket_exists(
                    guild.id, ticket_id
                )
                if ticket_exists:
                    notes = await self.bot.data_manager.get_ticket_note_history(
                        guild.id, ticket_id
                    )
                else:
                    await interaction.followup.send(
                        embed=Embeds.error(
                            description="❌ No ticket found with that ID."
                        )
                    )
                    return

            elif user:
                notes = await self.bot.data_manager.get_user_note_history(
                    guild.id, user.id
                )
            if not notes:
                await interaction.followup.send(
                    embed=Embeds.error(description="❌ No notes found.")
                )
                return

            pages = []
            for i in range(0, len(notes), 5):
                chunk = notes[i : i + 5]
                notes_embed = Embeds.success(title="Notes")
                if ticket_id:
                    notes_embed.set_author(
                        name=f"Ticket ID: {ticket_id}",
                    )
                elif user:
                    notes_embed.set_author(
                        name=f"{user.name} | {user.id}",
                        icon_url=user.display_avatar.url,
                    )

                for index, note in enumerate(chunk, start=i + 1):
                    note_id = note[0]
                    user_id = note[2]
                    ticket_id = note[3]
                    log_id = note[4]
                    mod_id = note[5]
                    mod_name = note[6]
                    date = note[7]
                    content = note[8]

                    if len(content) > 800:
                        content = content[:797] + "..."
                    if ticket_id != -1:
                        notes_embed.add_field(
                            name=f"Note ID: {note_id}",
                            value=f"**Ticket ID:** {ticket_id}\n"
                            f"**Ticket log:** <#{log_id}>\n"
                            f"**Moderator:** {mod_name} ({mod_id})\n"
                            f"**Date:** <t:{date}:D> (<t:{date}:R>)\n"
                            f"**Content:** {content}\n{'⎯' * 20}",
                            inline=False,
                        )
                    else:
                        notes_embed.add_field(
                            name=f"Note ID: {note_id}",
                            value=f"**User:** <@{user_id}> ({user_id})\n"
                            f"**Moderator:** {mod_name} ({mod_id})\n"
                            f"**Date:** <t:{date}:D> (<t:{date}:R>)\n"
                            f"**Content:** {content}\n{'⎯' * 20}",
                            inline=False,
                        )
                pages.append(notes_embed)

            pages = add_footers(pages)
            view = Paginator(pages)
            view.message = await interaction.followup.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/note view sent an error: {e}")

    @note_group.command(name="remove", description="Remove a note by its ID")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(note_id="Note ID to remove")
    async def remove_note(self, interaction: discord.Interaction, note_id: int):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            note_exists = await self.bot.data_manager.check_note_exists(
                note_id, guild.id
            )

            if note_exists:
                await self.bot.data_manager.remove_note(note_id, guild.id)
                await interaction.followup.send(
                    embed=Embeds.success(description=f"✅ Removed note **{note_id}**.")
                )
            else:
                await interaction.followup.send(
                    embed=Embeds.error(description="❌ No note found with that ID.")
                )

        except Exception as e:
            raise BotError(f"/note add_ticket sent an error: {e}")

    @commands.command(name="blacklist", aliases=["b"])
    @checks.is_user()
    @checks.is_guild()
    async def blacklist(
        self, ctx: commands.Context, user: discord.User, *, reason: str
    ):
        try:
            guild = ctx.guild
            blacklisted = await self.bot.data_manager.get_blacklist_entry(
                guild.id, user.id
            )

            if blacklisted is None:
                await self.bot.data_manager.add_blacklist_entry(
                    guild.id, user.id, reason, ctx.author
                )
                await ctx.send(
                    embed=Embeds.success(
                        description=(
                            f"✅ **{user.name}** ({user.id}) has been blacklisted from "
                            f"opening tickets\n**Reason:** {reason}"
                        )
                    )
                )
            else:
                await ctx.send(
                    embed=Embeds.error(description="❌ User is already blacklisted.")
                )

        except Exception as e:
            logger.exception(f"blacklist error: {e}")
            raise BotError(f"/blacklist sent an error: {e}")

    @commands.command(name="blacklist_view", aliases=["bv"])
    @checks.is_user()
    @checks.is_guild()
    async def blacklist_view(self, ctx: commands.Context):
        try:
            pages = []
            guild = ctx.guild

            blacklist_embed = Embeds.success(
                title=f"Server Blacklist",
                description="No blacklisted members found.",
            )
            url = None
            if guild.icon:
                url = guild.icon.url
            blacklist_embed.set_author(name=guild.name, icon_url=url)

            entries = await self.bot.data_manager.get_all_blacklist_from_db(guild.id)
            if not entries:
                await ctx.send(embed=blacklist_embed)
                return

            else:
                for i in range(0, len(entries), 5):
                    chunk = entries[i : i + 5]
                    blacklist_embed = Embeds.success(title=f"Server Blacklist")
                    blacklist_embed.set_author(name=guild.name, icon_url=url)

                    for index, entry in enumerate(chunk, start=i + 1):
                        user_id = entry[1]
                        reason = entry[2]
                        mod_id = entry[3]
                        modName = entry[4]
                        date = entry[5]

                        if len(reason) > 800:
                            reason = reason[:797] + "..."

                        blacklist_embed.add_field(
                            name=f"Case {index}",
                            value=f"**User:** <@{user_id}> ({user_id})\n"
                            f"**Moderator:** {modName} ({mod_id})\n"
                            f"**Date:** <t:{date}:D> (<t:{date}:R>)\n"
                            f"**Reason:** {reason}\n{'⎯' * 20}",
                            inline=False,
                        )
                    pages.append(blacklist_embed)

            pages = add_footers(pages)
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            logger.exception(f"blacklist_view error: {e}")
            raise BotError(f"/blacklist_view sent an error: {e}")

    @commands.command(name="whitelist", aliases=["w"])
    @checks.is_user()
    @checks.is_guild()
    async def whitelist(self, ctx: commands.Context, user: discord.User):
        try:
            guild = ctx.guild
            blacklisted = await self.bot.data_manager.get_blacklist_entry(
                guild.id, user.id
            )

            if blacklisted:
                await self.bot.data_manager.delete_blacklist_entry(guild.id, user.id)
                await ctx.send(
                    embed=Embeds.success(
                        description=(
                            f"✅ **{user.name}** ({user.id}) "
                            "has been removed from the blacklist"
                        )
                    )
                )
            else:
                await ctx.send(
                    embed=Embeds.error(description="❌ User is not blacklisted.")
                )

        except Exception as e:
            logger.exception(f"whitelist error: {e}")
            raise BotError(f"/whitelist sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
