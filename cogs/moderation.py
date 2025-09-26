import asyncio
import datetime
import re

import discord
from discord import app_commands
from discord.ext import commands

from classes.error_handler import *
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
            count = 0
            limit = 0

            historyEmbed = discord.Embed(
                title="Ticket History",
                description="User has not opened any tickets",
                color=discord.Color.green(),
            )
            historyEmbed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )

            history = await self.bot.data_manager.get_ticket_history(
                ctx.guild.id, user.id
            )
            if history is not None:
                if len(history) == 0:
                    await ctx.send(embed=historyEmbed)
                    return
                else:
                    page_counts = Paginator.build_subsections(len(history), 4)
                    for page_count in page_counts:
                        limit += page_count
                        historyEmbed = discord.Embed(
                            title="Ticket History",
                            description="Tickets are displayed by most recent open date.\n"
                            "Logs may appear as `#unknown` before being accessed.",
                            color=discord.Color.green(),
                        )

                        historyEmbed.set_author(
                            name=f"{user.name} | {user.id}",
                            icon_url=(user.avatar and user.avatar.url)
                            or user.display_avatar.url,
                        )

                        while count < limit:
                            ticket = history[count]

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
                                name=f"{count + 1}) {typeName} Ticket: {state}",
                                value=f"`ID: {ticket_id}`\n**Opened:** <t:{date_open}:D>\n**Closed:** {date_close}\n"
                                f"**Closed By:** {close_id}\n**Logs:** <#{log_id}>\n{'⎯' * 20}",
                                inline=False,
                            )
                            count += 1
                        pages.append(historyEmbed)

            for page in range(len(pages)):
                pages[page].set_footer(
                    text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})"
                )

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/ticket_history sent an error: {e}")

    @commands.command(name="noteadd")
    @checks.is_user()
    @checks.is_guild()
    async def notes_add(self, ctx, target, *, note: str):
        try:
            guild = ctx.guild
            channel = ctx.channel
            author = ctx.author
            content = await self.bot.helper.convert_mentions(note, guild)

            errorEmbed = discord.Embed(
                description="❌ Entered ID must be an integer",
                color=discord.Color.red(),
            )
            if target.isdigit():
                if int(target) < 9999999:
                    result = await self.bot.data_manager.check_ID_exists(
                        int(target), guild.id
                    )

                    if len(result) < 1:
                        errorEmbed.description = "❌ No ticket found with that ID"
                        await ctx.send(embed=errorEmbed)
                        return
                    else:
                        if len(content) > 1000:
                            errorEmbed.description = (
                                "❌ Notes must be 1000 characters or less"
                            )
                            await ctx.send(embed=errorEmbed)
                            return

                        await self.bot.data_manager.add_note(
                            guild.id,
                            result[0][0],
                            target,
                            author.id,
                            author.name,
                            content,
                        )
                        successEmbed = discord.Embed(
                            description=f"✅ Saved note for ticket ID **{target}**",
                            color=discord.Color.green(),
                        )
                        await ctx.send(embed=successEmbed)
                        return
                else:
                    member = await self.bot.cache.get_guild_member(guild, int(target))
                    if member is None:
                        errorEmbed.description = "❌ No member found with that ID"
                        await ctx.send(embed=errorEmbed)
                        return
                    else:
                        if len(content) > 1000:
                            errorEmbed.description = (
                                "❌ Notes must be 1000 characters or less"
                            )
                            await ctx.send(embed=errorEmbed)
                            return

                        await self.bot.data_manager.add_note(
                            guild.id, member.id, -1, author.id, author.name, content
                        )
                        successEmbed = discord.Embed(
                            description=f"✅ Saved note for **{member.name}** ({member.id})",
                            color=discord.Color.green(),
                        )
                        await ctx.send(embed=successEmbed)
                        return
            else:
                await ctx.send(embed=errorEmbed)
                return

            # await self.bot.data_manager.add_note()
        except Exception as e:
            raise BotError(f"+noteadd sent an error: {e}")

    @commands.command(name="notes")
    @checks.is_user()
    @checks.is_guild()
    async def notes(self, ctx, target):
        try:
            errorEmbed = discord.Embed(
                description="❌ This command is currently disabled for testing.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=errorEmbed)
            return
            # guild = ctx.guild
            # channel = ctx.channel
            # errorEmbed = discord.Embed(description="❌ Entered ID must be an integer",
            #                            color=discord.Color.red())
            # if target.isdigit():
            #     if int(target) < 9999999:
            #         result = await self.bot.data_manager.check_ID_exists(int(target), guild.id)
            #         print("result is", result)
            #         if len(result) < 1:
            #             errorEmbed.description=("❌ No ticket found with that ID")
            #             await ctx.send(embed=errorEmbed)
            #             return
            #         else:
            #             print("get notes for ticket", target)
            #     else:
            #         member = await self.bot.cache.get_guild_member(guild, int(target))
            #         if member is None:
            #             errorEmbed.description=("❌ No member found with that ID")
            #             await ctx.send(embed=errorEmbed)
            #             return
            #         else:
            #             print("get notes for member", target)
            # elif (re.search(r"<@!?(\d+)>", target)):
            #     id = (re.search(r"<@!?(\d+)>", target)).group(1)
            #     member = await self.bot.cache.get_guild_member(guild, int(id))
            #     if member is None:
            #         errorEmbed.description=("❌ No member found with that mention")
            #         await ctx.send(embed=errorEmbed)
            #         return
            #     else:
            #         print("get notes for member", target)
            # else:
            #     await ctx.send(embed=errorEmbed)
            #     return

            # FIXME get list to be processed

            # pages = []
            # count = 0
            # limit = 0
            # guild = ctx.guild

            # blacklist_embed = discord.Embed(title=f"Server Blacklist",
            #                       description="No blacklisted members found",
            #                       color=discord.Color.green())
            # url = None
            # if (guild.icon):
            #     url = guild.icon.url
            # blacklist_embed.set_author(name=guild.name, icon_url=url)

            # entries = await self.bot.data_manager.get_all_blacklist_from_db(guild.id)
            # if entries is not None:
            #     if len(entries) == 0:
            #         await ctx.send(embed=blacklist_embed)
            #         return
            #     else:
            #         page_counts = build_subsections(len(entries), 5)
            #         for page_count in page_counts:
            #             limit += page_count
            #             blacklist_embed = discord.Embed(title=f"Server Blacklist",
            #                     description="",
            #                     color=discord.Color.green())
            #             blacklist_embed.set_author(name=guild.name, icon_url=url)

            #             while (count < limit):
            #                 entry = entries[count]

            #                 user_id = entry[1]
            #                 reason = entry[2]
            #                 mod_id = entry[3]
            #                 modName = entry[4]
            #                 date = entry[5]

            #                 if len(reason) > 800:
            #                     reason = reason[:797] + "..."

            #                 blacklist_embed.add_field(name=f"Case {count + 1}",
            #                                 value=f"**User:** <@{user_id}> ({user_id})\n"
            #                                 f"**Moderator:** {modName} ({mod_id})\n"
            #                                 f"**Date:** <t:{date}:D> (<t:{date}:R>)\n"
            #                                 f"**Reason:** {reason}\n{'⎯' * 20}",
            #                                 inline=False)
            #                 count += 1
            #             pages.append(blacklist_embed)

            # for page in range(len(pages)):
            #     pages[page].set_footer(text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})")

            # # Create an instance of the pagination view
            # view = Paginator(pages)
            # view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            logger.exception(f"+notes error: {e}")
            raise BotError(f"+notes sent an error: {e}")

    note_group = app_commands.Group(name="note", description="Manage notes")

    @note_group.command(name="add", description="Add a note to a ticket or user")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(ticket_id="The ticket ID to add a note to")
    @app_commands.describe(user="The user to add a note to")
    @app_commands.describe(note="The content of the note")
    async def note_add(
        self,
        interaction: discord.Interaction,
        ticket_id: int = None,
        user: discord.Member = None,
        note: str = None,
    ):
        try:
            errorEmbed = discord.Embed(
                description="❌ This command is currently disabled for testing.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)
            return

        except Exception as e:
            raise BotError(f"/note add sent an error: {e}")

    @note_group.command(name="view", description="Add a note to a ticket or user")
    @checks.is_user_app()
    @checks.is_guild_app()
    @app_commands.describe(ticket_id="The ticket ID to add a note to")
    @app_commands.describe(user="The user to add a note to")
    async def view(
        self,
        interaction: discord.Interaction,
        ticket_id: int = None,
        user: discord.Member = None,
        note: str = None,
    ):
        try:
            errorEmbed = discord.Embed(
                description="❌ This command is currently disabled for testing.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)
            return

        except Exception as e:
            raise BotError(f"/note view sent an error: {e}")

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
            result_embed = discord.Embed(
                description=f"❌ **{user.name}** ({user.id}) is already blacklisted",
                color=discord.Color.red(),
            )

            if blacklisted is None:
                await self.bot.data_manager.add_blacklist_entry(
                    guild.id, user.id, reason, ctx.author
                )
                result_embed.description = (
                    f"✅ **{user.name}** ({user.id}) has been blacklisted from "
                    f"opening tickets\n**Reason:** {reason}"
                )
                result_embed.color = discord.Color.green()

            await ctx.send(embed=result_embed)

        except Exception as e:
            logger.exception(f"blacklist error: {e}")
            raise BotError(f"/blacklist sent an error: {e}")

    @commands.command(name="blacklist_view", aliases=["bv"])
    @checks.is_user()
    @checks.is_guild()
    async def blacklist_view(self, ctx: commands.Context):
        try:
            pages = []
            count = 0
            limit = 0
            guild = ctx.guild

            blacklist_embed = discord.Embed(
                title=f"Server Blacklist",
                description="No blacklisted members found",
                color=discord.Color.green(),
            )
            url = None
            if guild.icon:
                url = guild.icon.url
            blacklist_embed.set_author(name=guild.name, icon_url=url)

            entries = await self.bot.data_manager.get_all_blacklist_from_db(guild.id)
            if entries is not None:
                if len(entries) == 0:
                    await ctx.send(embed=blacklist_embed)
                    return
                else:
                    page_counts = Paginator.build_subsections(len(entries), 5)
                    for page_count in page_counts:
                        limit += page_count
                        blacklist_embed = discord.Embed(
                            title=f"Server Blacklist",
                            description="",
                            color=discord.Color.green(),
                        )
                        blacklist_embed.set_author(name=guild.name, icon_url=url)

                        while count < limit:
                            entry = entries[count]

                            user_id = entry[1]
                            reason = entry[2]
                            mod_id = entry[3]
                            modName = entry[4]
                            date = entry[5]

                            if len(reason) > 800:
                                reason = reason[:797] + "..."

                            blacklist_embed.add_field(
                                name=f"Case {count + 1}",
                                value=f"**User:** <@{user_id}> ({user_id})\n"
                                f"**Moderator:** {modName} ({mod_id})\n"
                                f"**Date:** <t:{date}:D> (<t:{date}:R>)\n"
                                f"**Reason:** {reason}\n{'⎯' * 20}",
                                inline=False,
                            )
                            count += 1
                        pages.append(blacklist_embed)

            for page in range(len(pages)):
                pages[page].set_footer(
                    text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})"
                )

            # Create an instance of the pagination view
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
            result_embed = discord.Embed(
                description=f"❌ **{user.name}** ({user.id}) is not blacklisted",
                color=discord.Color.red(),
            )

            if blacklisted is not None:
                await self.bot.data_manager.delete_blacklist_entry(guild.id, user.id)
                result_embed.description = f"✅ **{user.name}** ({user.id}) has been removed from the blacklist"
                result_embed.color = discord.Color.green()

            await ctx.send(embed=result_embed)

        except Exception as e:
            logger.exception(f"whitelist error: {e}")
            raise BotError(f"/whitelist sent an error: {e}")

    @commands.command(name="verbal")
    @checks.is_user()
    @checks.is_guild()
    async def verbal(self, ctx, user: discord.Member, *, reason: str):
        try:
            guild = ctx.guild
            author = ctx.author
            sent_message = None
            dm_channel = user.dm_channel or await user.create_dm()

            reason = await self.bot.helper.convert_mentions(reason, guild)

            if len(reason) > 800:
                embed = discord.Embed(
                    description="❌ Reason length is too long, it must be at most 800 characters"
                    "\n\nNote that channel links add approximately 70 characters each",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            verbal_embed = discord.Embed(
                title="Verbal Warning",
                description=f"**{reason}**",
                color=discord.Color.blue(),
            )
            verbal_embed.set_footer(
                text="This does NOT count as a moderation warning. If you have any questions, "
                f"please reach out to us via ModMail."
            )
            if guild.icon:
                verbal_embed.set_author(name=f"{guild.name}", icon_url=guild.icon.url)
            else:
                verbal_embed.set_author(name=f"{guild.name}")

            if dm_channel:
                try:
                    sent_message = await dm_channel.send(embed=verbal_embed)

                except discord.Forbidden:
                    embed = discord.Embed(
                        description="❌ Failed to DM user, they may not be accepting DMs",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                except Exception:
                    embed = discord.Embed(
                        description="❌ Failed to DM user", color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
            else:
                embed = discord.Embed(
                    description="❌ Could not create a DM channel with the user",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            await self.bot.data_manager.add_verbal(
                sent_message.id, guild.id, user.id, author.id, author.name, reason
            )

            successEmbed = discord.Embed(
                description=f"✅ **Verbally warned <@{user.id}> ({user.name})**",
                color=discord.Color.green(),
            )
            successEmbed.add_field(name="Reason", value=reason, inline=False)
            successEmbed.add_field(
                name="Verbal ID", value=f"```{sent_message.id}```", inline=False
            )
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal error: {e}")
            raise BotError(f"/verbal sent an error: {e}")

    @commands.command(name="verbal_edit")
    @checks.is_user()
    @checks.is_guild()
    async def verbal_edit(self, ctx, verbal_id: str, *, new_reason: str):
        try:
            guild = ctx.guild
            author = ctx.author
            user_id = None
            user = None
            old_reason = None
            new_reason = await self.bot.helper.convert_mentions(new_reason, guild)

            if len(new_reason) > 800:
                embed = discord.Embed(
                    description="❌ New reason length is too long, it must be at most 800 characters"
                    "\n\nNote that channel links add approximately 70 characters each",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            result = await self.bot.data_manager.get_verbal(verbal_id)
            if len(result) != 0:
                user_id = result[0][2]
                old_reason = result[0][6]
            else:
                embed = discord.Embed(
                    description="❌ Verbal not found, invalid ID",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            try:
                user = await asyncio.wait_for(guild.fetch_member(user_id), timeout=1)
            except Exception:
                try:
                    user = await asyncio.wait_for(
                        guild.fetch_member(user_id), timeout=1
                    )
                except Exception:
                    embed = discord.Embed(
                        description="❌ User not found, if this command fails "
                        "again the user does not exist (or Discord's API is down)",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

            dm_channel = user.dm_channel or await user.create_dm()

            if dm_channel:
                try:
                    sent_message = await dm_channel.fetch_message(int(verbal_id))

                except discord.NotFound:
                    embed = discord.Embed(
                        description="❌ Verbal not found, invalid user or ID",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                except discord.Forbidden:
                    embed = discord.Embed(
                        description="❌ Unable to edit verbal, user may not be accepting DMs",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                except Exception:
                    embed = discord.Embed(
                        description="❌ Unable to find verbal",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                newEmbed = sent_message.embeds[0]
                newEmbed.description = new_reason
                await sent_message.edit(embed=newEmbed)

            else:
                embed = discord.Embed(
                    description="❌ Could not create a DM channel with the user",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            await self.bot.data_manager.edit_verbal(
                verbal_id, author.id, author.name, new_reason
            )

            successEmbed = discord.Embed(
                description=f"✅ **Updated verbal for <@{user.id}> ({user.name})**",
                color=discord.Color.green(),
            )
            successEmbed.add_field(name="Old Reason", value=old_reason, inline=False)
            successEmbed.add_field(name="New Reason", value=new_reason, inline=False)
            successEmbed.add_field(
                name="Verbal ID", value=f"```{verbal_id}```", inline=False
            )
            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal_edit error: {e}")
            raise BotError(f"/verbal_edit sent an error: {e}")

    @commands.command(name="verbal_delete")
    @checks.is_user()
    @checks.is_guild()
    async def verbal_delete(self, ctx, verbal_id: str):
        try:
            guild = ctx.guild
            user_id = None
            user = None

            result = await self.bot.data_manager.get_verbal(verbal_id)
            if len(result) != 0:
                user_id = result[0][3]
            else:
                embed = discord.Embed(
                    description="❌ Verbal not found, invalid ID",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            try:
                user = await asyncio.wait_for(guild.fetch_member(user_id), timeout=1)
            except Exception:
                try:
                    user = await asyncio.wait_for(
                        guild.fetch_member(user_id), timeout=1
                    )
                except Exception:
                    embed = discord.Embed(
                        description="❌ User not found, if this command fails "
                        "again the user does not exist (or Discord's API is down)",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

            dm_channel = user.dm_channel or await user.create_dm()

            if dm_channel:
                try:
                    message = await dm_channel.fetch_message(int(verbal_id))
                except discord.NotFound:
                    embed = discord.Embed(
                        description="❌ Verbal not found, invalid user or ID",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                except discord.Forbidden:
                    embed = discord.Embed(
                        description="❌ Unable to delete verbal, user may not be accepting DMs",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                except Exception:
                    embed = discord.Embed(
                        description="❌ Unable to find verbal",
                        color=discord.Color.red(),
                    )
                    await ctx.send(embed=embed)
                    return

                await message.delete()

            else:
                embed = discord.Embed(
                    description="❌ Could not create a DM channel with the user",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            await self.bot.data_manager.remove_verbal(verbal_id)

            successEmbed = discord.Embed(
                description=f"✅ **Deleted verbal `{verbal_id}` from <@{user.id}> ({user.name})**",
                color=discord.Color.green(),
            )

            await ctx.send(embed=successEmbed)

        except Exception as e:
            logger.exception(f"verbal_delete error: {e}")
            raise BotError(f"/verbal_delete sent an error: {e}")

    @commands.command(name="verbal_history")
    @checks.is_user()
    @checks.is_guild()
    async def verbal_history(self, ctx: commands.Context, user: discord.Member):
        try:
            pages = []
            count = 0
            limit = 0
            guild = ctx.guild

            historyEmbed = discord.Embed(
                title=f"Verbal history for {user.name}",
                description="User does not have any verbals",
                color=discord.Color.green(),
            )

            historyEmbed.set_author(
                name=f"{user.name} | {user.id}",
                icon_url=(user.avatar and user.avatar.url) or user.display_avatar.url,
            )

            history = await self.bot.data_manager.get_verbal_history(guild.id, user.id)
            if history is not None:
                if len(history) == 0:
                    await ctx.send(embed=historyEmbed)
                    return
                else:
                    page_counts = Paginator.build_subsections(len(history), 3)
                    for page_count in page_counts:
                        limit += page_count
                        historyEmbed = discord.Embed(
                            title=f"Verbal history for {user.name}",
                            description="",
                            color=discord.Color.green(),
                        )

                        historyEmbed.set_author(
                            name=f"{user.name} | {user.id}",
                            icon_url=(user.avatar and user.avatar.url)
                            or user.display_avatar.url,
                        )

                        while count < limit:
                            verbal = history[count]

                            verbal_id = verbal[0]
                            author_id = verbal[1]
                            authorName = verbal[2]
                            date = verbal[3]
                            content = verbal[4]

                            # member = guild.get_member(user_id)
                            # if not member:
                            #     member = await guild.fetch_member(user_id)

                            #     await asyncio.wait_for(self.bot.fetch_channel(inbox_id), timeout=1)

                            historyEmbed.add_field(
                                name=f"Case {count + 1}",
                                value=f"**Moderator:** {authorName} ({author_id})\n"
                                f"**Date:** <t:{date}:D> (<t:{date}:R>)\n**Reason:** {content}\n"
                                f"**Verbal ID:**```{verbal_id}```{'⎯' * 20}",
                                inline=False,
                            )
                            historyEmbed.add_field
                            count += 1
                        pages.append(historyEmbed)

            for page in range(len(pages)):
                pages[page].set_footer(
                    text=f"Use the buttons below to navigate (Page {page + 1}/{len(pages)})"
                )

            # Create an instance of the pagination view
            view = Paginator(pages)
            view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            raise BotError(f"/verbal_history sent an error: {e}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
