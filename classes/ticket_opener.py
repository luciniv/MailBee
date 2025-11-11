import asyncio
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List

import discord
from discord import Embed
from discord.permissions import PermissionOverwrite

from classes.helpers import Ticket
from roblox_data.roblox import *
from utils.logger import *


async def get_overwrites(guild, roles) -> Dict:
    """
    Generate permission overwrites for a ticket channel.
    """
    overwrites = {guild.default_role: PermissionOverwrite(read_messages=False)}

    for role in roles:
        if role is not None:
            overwrites[role] = PermissionOverwrite(
                read_messages=True,
                read_message_history=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
            )
    return dict(overwrites)


class AddInfoButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # no timeout needed
        self.add_item(
            discord.ui.Button(
                label="Send more messages in this DM!",
                style=discord.ButtonStyle.blurple,
                disabled=True,
            )
        )


class TicketOpener:
    def __init__(self, bot):
        self.bot = bot

    async def open_ticket(self, ticket: Ticket):
        try:
            user_id = ticket.user_id
            guild_id = ticket.guild_id
            category_id = ticket.category_id
            dm_message_id = ticket.dm_message_id
            user = await self.bot.cache.get_user(user_id)
            if not user:
                print("Failed to fetch user for ticket opener, re-added ticket")
                await self.bot.ticket_queue._re_add_ticket(ticket)

            guild = self.bot.get_guild(guild_id)
            category = guild.get_channel(category_id)

            type_name = ticket.type_name
            nsfw = ticket.nsfw

            error_embed = discord.Embed(description="", color=discord.Color.red())

            # Generate ticket ID
            ticket_id = await self.bot.data_manager.get_next_ticket_id(guild.id)
            dm_channel = user.dm_channel or await user.create_dm()
            if dm_channel is None:
                return

            # Get info message
            info_message = await self.bot.cache.get_message(dm_channel, dm_message_id)

            # Create log embed
            log_channel = None
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            if config is None:
                pass
            else:
                log_id = config["log_id"]
                log_channel = await self.bot.cache.get_channel(log_id)

                log_embed = discord.Embed(
                    title=f"{'🔞' if nsfw else ''} New \"{type_name}\" Ticket",
                    description="",
                    color=discord.Color.green(),
                )
                log_embed.timestamp = datetime.now(timezone.utc)
                log_embed.set_footer(
                    text=f"{user.name} | {user.id}",
                    icon_url=(user.avatar and user.avatar.url)
                    or user.display_avatar.url,
                )

            # Send log embed
            log_message = None
            if log_channel:
                try:
                    log_message = await log_channel.send(embed=log_embed)
                except Exception:
                    pass
            else:
                error_embed.description = (
                    "❌ Could not find ticket logging channel in destination server. ",
                    "Please try again or contact a server admin if this issue persists.",
                )
                await dm_channel.send(embed=error_embed)
                return False

            # Create logging thread
            if log_message:
                try:
                    thread = await log_message.create_thread(
                        name=f"Ticket Log {user.name} - {ticket_id}",
                        auto_archive_duration=1440,
                    )
                except discord.HTTPException as e:
                    if "Contains words not allowed" in e.text:
                        thread = await log_message.create_thread(
                            name=f"Ticket Log {user.id} - {ticket_id}",
                            auto_archive_duration=1440,
                        )
                except Exception:
                    pass

                if thread is not None:
                    await self.bot.cache.store_channel(thread)
                else:
                    error_embed.description = "❌ Unable to create logging thread. Contact a server admin with this error."
                    await dm_channel.send(embed=error_embed)
                    return False
            else:
                error_embed.description = "❌ Unable to send opening log. Contact a server admin with this error."
                await dm_channel.send(embed=error_embed)
                return False

            # Create ticket channel
            channel = await self.create_ticket_channel(
                guild, category, user, thread.id, nsfw
            )
            if channel is None:
                error_embed.description = (
                    "Thank you for reaching out to the moderation team!\n\n"
                    f"Unfortunately, tickets of type **{type_name}** have "
                    "reached maximum capacity. Please try again later for an "
                    "opening, we thank you in advance for your patience.",
                )
                await dm_channel.send(embed=error_embed)
                await thread.delete()
                await log_message.delete()
                return False
            await self.bot.cache.store_channel(channel)

            # Add new ticket to database + refresh tickets
            await self.bot.data_manager.create_ticket(
                ticket, channel.id, ticket_id, thread.id
            )
            await self.bot.data_manager.get_or_load_user_tickets(user.id, False)

            # Task for sending server info
            server = asyncio.create_task(
                self.handle_server_embeds(
                    ticket,
                    guild,
                    channel,
                    thread,
                    user,
                    ticket_id,
                )
            )
            # Task for sending dm info
            dm = asyncio.create_task(
                self.handle_dm_embeds(guild, dm_channel, user, ticket.data, type_name)
            )

            # Delete info message
            if info_message:
                await info_message.delete()

            # Finish log embed
            log_embed.add_field(
                name="Ticket Channel", value=f"<#{channel.id}>", inline=True
            )
            log_embed.add_field(name="Ticket ID", value=ticket_id, inline=True)
            await log_message.edit(embed=log_embed)
            await server, dm
            return True

        except Exception as e:
            logger.exception("ticket_opener sent an exception:", e)

    async def create_ticket_channel(self, guild, category, user, threadID, NSFW):
        try:
            channel_name = re.sub(r"[./]", "", user.name.lower())
            try:
                ticket_channel = await guild.create_text_channel(
                    name=f"{'🆕🔞' if NSFW else '🆕'}{channel_name}",
                    nsfw=NSFW,
                    category=category,
                    overwrites=category.overwrites,
                    topic=f"Ticket channel {user.id} {threadID}",
                )

            except discord.HTTPException as e:
                if "Contains words not allowed" in e.text:
                    ticket_channel = await guild.create_text_channel(
                        name=str(user.id),
                        nsfw=NSFW,
                        category=category,
                        overwrites=category.overwrites,
                        topic=f"Ticket channel {user.id} {threadID}",
                    )
            except Exception:
                return None
            return ticket_channel

        except Exception as e:
            logger.exception(f"create channel exception: {e}")
            return None

    async def handle_server_embeds(
        self, ticket, guild, channel, thread, user, ticket_id
    ):

        member = await self.bot.cache.get_guild_member(guild, user.id)

        if member is None:
            logger.warning(f"Failed to find member object for user once: {user.id}")
            member = await self.bot.cache.get_guild_member(guild, user.id)
            if member is None:
                logger.error("Creating ticket embeds without member object")
                member = None

        count = await self.bot.data_manager.get_ticket_count(guild.id, user.id)
        if count is not None:
            count = int(count[0][0])
            if count != 0:
                count -= 1
        else:
            count = 0

        ticket_embed = discord.Embed(
            title=f'New "{ticket.type_name}" Ticket [ID {ticket_id}]',
            description="To reply, send a message in this channel prefixed with `+`. "
            "Any other messages will send as a comment (not visible to the ticket opener). "
            "To use commands, prefix with `+` or type `/` and select from the displayed "
            "list.\n\n`+close [reason]` will close a ticket. `+inactive [hours] [reason]` "
            "will close a ticket after X hours of inactivity from the ticket opener.",
        )
        ticket_embed.timestamp = datetime.now(timezone.utc)
        name = f"{user.name} | {user.id}"
        if member is not None:
            ticket_embed.set_footer(
                text=name,
                icon_url=(
                    (member.avatar and member.avatar.url) or member.display_avatar.url
                ),
            )
        else:
            ticket_embed.set_footer(
                text=name, icon_url=((user.avatar and user.avatar.url) or None)
            )

        # Populate ticket info embed depending on the member object existing
        ticket_embed.add_field(name="Opener @", value=f"<@{user.id}>", inline=True)
        ticket_embed.add_field(name="Opener ID", value=user.id, inline=True)
        # Member-specific info
        if member is not None:
            roles = member.roles
            default = guild.default_role
            formatted_roles = "*None*"
            if len(roles) > 1:
                formatted_roles = " ".join(
                    [f"<@&{role.id}>" for role in roles if role != default]
                )
                if len(formatted_roles) > 1024:
                    formatted_roles = (
                        f"*{len([role for role in roles if role != default])} roles*"
                    )
            ticket_embed.add_field(name="Roles", value=formatted_roles, inline=True)
            ticket_embed.add_field(name="", value="", inline=False)
            ticket_embed.add_field(
                name="Join Date",
                value=f"<t:{int(member.joined_at.timestamp())}:R>",
                inline=True,
            )
            ticket_embed.add_field(
                name="Account Age",
                value=f"<t:{int(user.created_at.timestamp())}:R>",
                inline=True,
            )
            roblox_username = (
                ticket.roblox_username if ticket.roblox_username else "N/A"
            )
            roblox_id = ticket.roblox_id if ticket.roblox_id != -1 else "N/A"
            robux_spent = ticket.robux_spent if ticket.robux_spent != -1 else "N/A"
            hours_played = ticket.hours_played if ticket.hours_played != -1 else "N/A"

            ticket_embed.add_field(name="", value="", inline=False)
            ticket_embed.add_field(
                name="Roblox Username", value=roblox_username, inline=True
            )
            ticket_embed.add_field(name="Roblox ID", value=roblox_id, inline=True)
            ticket_embed.add_field(name="", value="", inline=False)
            ticket_embed.add_field(name="Robux Spent", value=robux_spent, inline=True)
            ticket_embed.add_field(name="Hours Ingame", value=hours_played, inline=True)

        # Member-nonspecific info
        ticket_embed.add_field(name="", value="", inline=False)
        ticket_embed.add_field(
            name="Time Taken on Form",
            value=f"`{ticket.time_taken}` seconds",
            inline=True,
        )
        ticket_embed.add_field(name="Prior Tickets", value=count, inline=True)

        submission_embed = await self.create_submission_embed(
            None, user, ticket.data, ticket.type_name
        )

        pings = None
        if ticket.ping_roles:
            pings = " ".join([f"<@&{role}>" for role in ticket.ping_roles])

        await channel.send(pings, embeds=[ticket_embed, submission_embed])
        await thread.send(embeds=[ticket_embed, submission_embed])

    async def handle_dm_embeds(self, guild, dm_channel, user, values, type_name):

        config = await self.bot.data_manager.get_or_load_config(guild.id)

        dm_embed = discord.Embed(
            title=f'New "{type_name}" Ticket',
            description=f"You have opened a new ticket with {guild.name}\n\n"
            f"Send a message in this DM to speak to "
            f"the server's staff team. Run `/create_ticket` "
            f"to open a ticket with a different server. You may "
            f"only have one ticket open per server at a time.",
            color=discord.Color.blue(),
        )
        dm_embed.timestamp = datetime.now(timezone.utc)

        if guild.icon:
            dm_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
        else:
            dm_embed.set_footer(text=guild.name)

        greeting_embed = None
        if config is not None:
            greeting_text = config["greeting"]
            if len(greeting_text) == 0:
                greeting_text = (
                    "Hi {mention}, thanks for reaching out! We'll get back to you "
                    "as soon as we can.\n\nIn the meantime, please refer to the "
                    "informational channels in our server regarding MailBee and its "
                    "rules."
                )
            try:
                greeting = greeting_text.format(
                    mention=f"<@{user.id}>", name=user.name, id=user.id
                )
            except KeyError:
                return

            greeting_embed = discord.Embed(
                title="Greeting Message",
                description=greeting,
                color=discord.Color.blue(),
            )
            greeting_embed.timestamp = datetime.now(timezone.utc)

            if guild.icon:
                greeting_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                greeting_embed.set_footer(text=guild.name)

        submission_embed = await self.create_submission_embed(
            guild, None, values, type_name
        )

        info_embed = discord.Embed(
            description="**Tip**: Any messages sent in this DM will go to the staff team. "
            "If you have additional images / files to add to your ticket, **send "
            "them now.**"
        )
        info_embed.set_footer(
            text="This is an automated message. Further messages you may receive are from staff."
        )

        if greeting_embed:
            await dm_channel.send(
                embeds=[dm_embed, greeting_embed, submission_embed, info_embed]
            )
        else:
            await dm_channel.send(embeds=[dm_embed, submission_embed, info_embed])

    async def create_submission_embed(self, guild, member, values, type_name):
        submission_embed = discord.Embed(
            title=f'"{type_name}" Form Submission', color=discord.Color.green()
        )
        submission_embed.timestamp = datetime.now(timezone.utc)

        for label, answer in values.items():
            submission_embed.add_field(
                name=label, value=answer if answer.strip() else "N/A", inline=False
            )

        if guild is None:
            submission_embed.set_footer(
                text=f"{member.name} | {member.id}",
                icon_url=(member.avatar and member.avatar.url)
                or member.display_avatar.url,
            )
        else:
            if guild.icon:
                submission_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                submission_embed.set_footer(text=guild.name)

        return submission_embed

    async def priority(guild, user_id):
        priority_values = [-1, -1]
        game_type = SERVER_TO_GAME.get(guild.id, None)

        if game_type is not None:
            priority_values = await get_roblox_data(game_type, guild.id, user_id)

        if not priority_values:
            priority_values = [-1, -1]
