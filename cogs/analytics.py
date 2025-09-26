import asyncio
import io
import os
import re
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from classes.error_handler import *
from classes.ticket_submitter import TicketSelectView
from roblox_data.helpers import *
from utils import emojis
from utils.logger import *

SERVER_TO_GAME = {
    714722808009064492: ("Creatures of Sonaria", 1831550657, os.getenv("COS_KEY")),
    346515443869286410: ("Dragon Adventures", 1235188606, os.getenv("DA_KEY")),
    1196293227976863806: ("Horse Life", 5422546686, os.getenv("HL_KEY")),
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 20MB in bytes


class MessageReceivedButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # no timeout needed
        self.add_item(
            discord.ui.Button(
                label="Send a message to reply!",
                style=discord.ButtonStyle.blurple,
                disabled=True,
            )
        )


class Analytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processing_queue = asyncio.Queue()

    async def cog_load(self):
        pass
        # logger.log("SYSTEM", "------- CATCHING BACKLOG -----------------")
        # await self.catch_modmail_backlog()
        # await self.process_queue()

    async def bot_dm(self, message: discord.Message):
        try:
            channel = message.channel
            author_id = message.author.id
            tickets = await self.bot.data_manager.get_or_load_user_tickets(author_id)

            # Prompt to open a ticket
            if tickets is None:
                start_embed = discord.Embed(
                    title="Open a Ticket",
                    description='Click the **"Open a Ticket"** button in a server '
                    "you share with this bot to open a ticket!\n\nAlternatively, "
                    "use the `/create_ticket` command in this DM channel to open "
                    "a ticket with a selected server. You must be a member of the "
                    "server you wish to open a ticket with.",
                    color=discord.Color.blue(),
                )
                await channel.send(embed=start_embed)

            # Route message to open ticket
            elif len(tickets) == 1:
                ticket = tickets[0]
                guild_id = ticket["guild_id"]
                channel_id = ticket["channel_id"]
                await self.route_to_server(message, guild_id, channel_id)

            # Selection menu for where to route ticket message
            elif len(tickets) > 1:
                ticket_embed = discord.Embed(
                    title=(
                        "❗️You Have Multiple Tickets Open, Choose Your Message "
                        "Destination"
                    ),
                    description="Use the dropdown menu to select which server to "
                    "send your message to. These are servers you **currently have an "
                    "open ticket with**.\n\nIf you would like to create a new ticket "
                    "with a different server, use `/create_ticket`",
                    color=discord.Color.blue(),
                )
                view = TicketSelectView(self.bot, tickets, message)
                view_message = await channel.send(embed=ticket_embed, view=view)
                view.message = view_message

        except Exception as e:
            logger.exception(f"bot_dm sent an error: {e}")

    async def route_to_server(
        self, message: discord.Message, guild_id: int, channel_id: int
    ):
        try:
            error_embed = discord.Embed(
                description="❌ You are blacklisted from sending messages "
                "to this server.",
                color=discord.Color.red(),
            )
            # Check blacklist
            author = message.author
            entry = await self.bot.data_manager.get_blacklist_entry(guild_id, author.id)
            if entry is not None:
                await message.channel.send(embed=error_embed)
                return

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                error_embed.description = (
                    "❌ I could not find the server you are trying to contact. "
                    "Please try again later. If this error persists, then I am "
                    "not in that server."
                )
                await message.channel.send(embed=error_embed)
                return

            member = await self.bot.cache.get_guild_member(guild, author.id)
            if member is None:
                error_embed.description = (
                    "❌ You are not in the server you are trying to contact. Please "
                    "rejoin the server before attempting to send messages there.\n\n"
                    "If you ARE in the server, please re-try sending your message. "
                    "Discord API issues may prevent your messages from being sent."
                )
                await message.channel.send(embed=error_embed)
                return

            server_channel = await self.bot.cache.get_channel(channel_id)
            if server_channel is None:
                error_embed.description = (
                    "❌ Could not find your ticket channel in this server. "
                    "Please send your message again, or contact staff another "
                    "way if this error persists."
                )
                await message.channel.send(embed=error_embed)
                return

            id_list = (server_channel.topic).split()
            thread_id = id_list[-1]
            thread = await self.bot.cache.get_channel(thread_id)
            if thread is None:
                error_embed.description = (
                    "❌ Could not find your ticket log in this server. "
                    "Please send your message again, or contact staff another "
                    "way if this error persists."
                )
                await message.channel.send(embed=error_embed)
                return

            timestamp = datetime.now(timezone.utc)
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            snapshot_flag = False
            content = None
            content = message.content

            if content is None:
                error_embed.description = (
                    "❌ Failed to read forwarded message content. "
                    "Send the message via copy-paste instead."
                )
                await message.channel.send(embed=error_embed)
                return

            text = await self.bot.helper.convert_mentions(content, guild)

            # Check if over 4000 characters
            if len(text) > 4000:
                error_embed.description = (
                    "❌ Message must be less than 4000 characters. Note that "
                    "channel links add ~70 additional characters each."
                )
                await message.channel.send(embed=error_embed)
                return

            # NOTE file attachments
            # Process any attachments
            attachments = []
            final_attachments = []
            raw_files = []  # <-- store raw data
            files = []
            fileMessage = None
            file_embed = discord.Embed(
                title="",
                description="**Processing files...**\n"
                "Please note that image / video files may not send if they are too "
                "large (>10MB). For the fastest processing, upload large files to "
                "hosting websites and share links to the uploads instead.",
                color=discord.Color.blue(),
            )
            skipped_files = False
            if message:
                if snapshot_flag:
                    attachments = message.message_snapshots[0].message.attachments
                else:
                    attachments = message.attachments

                if len(attachments) > 0:
                    fileMessage = await message.channel.send(embed=file_embed)

                total_size = 0
                for file in attachments:
                    if file.size + total_size > MAX_FILE_SIZE:
                        skipped_files = True
                        continue
                    else:
                        final_attachments.append(file.url)
                    saved_file = io.BytesIO()
                    await file.save(saved_file)
                    raw_files.append(
                        (saved_file.getvalue(), file.filename)
                    )  # store raw bytes + filename
                    total_size += file.size

            if len(text) == 0 and len(final_attachments) == 0:
                empty_embed = discord.Embed(
                    description=(
                        "❌ Message not sent, you cannot send an empty or forwarded "
                        "message."
                    ),
                    color=discord.Color.red(),
                )
                await message.channel.send(embed=empty_embed)
                return

            reply_embed = discord.Embed(
                title="Message Sent", description=text, color=discord.Color.green()
            )
            reply_embed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                reply_embed.add_field(
                    name=f"Attachment {count}", value=url, inline=False
                )

            if guild.icon:
                reply_embed.set_footer(text=guild.name, icon_url=guild.icon.url)
            else:
                reply_embed.set_footer(text=guild.name)

            # Later, when sending:
            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            try:
                sent_message = await message.channel.send(
                    embed=reply_embed, files=files
                )
            except Exception:
                await message.add_reaction("❌")
                return

            if skipped_files:
                skip_embed = discord.Embed(
                    description="⚠️ Some attachments were skipped for being too "
                    "large or exceeding the total file size limit (10MB).",
                    color=discord.Color.yellow(),
                )
                await message.channel.send(embed=skip_embed)

            if fileMessage is not None:
                await fileMessage.delete()

            send_embed = discord.Embed(
                title="Message Received", description=text, color=discord.Color.green()
            )
            send_embed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                send_embed.add_field(
                    name=f"Attachment {count}", value=url, inline=False
                )
            send_embed.set_footer(
                text=f"{author.name} | {author.id}",
                icon_url=(author.avatar and author.avatar.url)
                or author.display_avatar.url,
            )

            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            try:
                await server_channel.send(embed=send_embed, files=files)
            except Exception:
                error_embed.description = (
                    "❌ Failed to send message to server. Please try again."
                )
                await message.channel.send(embed=error_embed)
                return

            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            try:
                await thread.send(
                    embed=send_embed,
                    files=files,
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
            except Exception:
                pass

            await self.bot.data_manager.add_ticket_message(
                sent_message.id,
                None,
                message.channel.id,
                author.id,
                format_time,
                "Received",
                True,
            )
            await self.bot.channel_status.remove_timer(server_channel.id)
            await self.bot.channel_status.set_emoji(server_channel, "alert")

        except Exception as e:
            await message.add_reaction("❌")
            logger.exception(f"route_to_server sent an error: {e}")

    async def route_to_dm(
        self,
        message,
        channel,
        author,
        thread_id: int,
        user_id: int,
        anon: bool = None,
        snippet: bool = None,
    ):
        try:
            member = None
            guild = channel.guild
            error_embed = discord.Embed(
                description="❌ Ticket opener is no longer in this server. Use "
                "`+close [reason]` to close this ticket.",
                color=discord.Color.red(),
            )
            member = await self.bot.cache.get_guild_member(guild, user_id)
            if member is None:
                try:
                    member = await asyncio.wait_for(
                        guild.fetch_member(user_id), timeout=1
                    )
                    if member is not None:
                        await self.bot.cache.store_guild_member(guild.id, member)
                except discord.NotFound:
                    await channel.send(embed=error_embed)
                    return
                except Exception:
                    error_embed.description = (
                        "❌ Error fetching ticket opener. Please try again shortly."
                    )
                    await channel.send(embed=error_embed)
                    return

            await self.bot.cache.store_guild_member(guild.id, author)

            # Check if blacklisted
            entry = await self.bot.data_manager.get_blacklist_entry(guild.id, user_id)
            if entry is not None:
                error_embed.description = (
                    "❌ Ticket opener is blacklisted. `+whitelist` them before "
                    "attempting to send a message."
                )
                await channel.send(embed=error_embed)
                return

            thread = await self.bot.cache.get_channel(thread_id)
            if thread is None:
                error_embed.description = (
                    "❌ Failed to fetch logging thread. Please re-send "
                    "your message again."
                )
                await channel.send(embed=error_embed)
                return

            content = message
            if isinstance(message, discord.Message):
                content = message.content

            # Clean remaining prefixes
            content = re.sub(
                r"^\+(?:(?:nonareply|areply|reply|nar|ar|r)\s+|\s*)",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = await self.bot.helper.convert_mentions(content, guild)

            # Check if over 4000 characters
            if len(content) > 4000:
                error_embed.description = (
                    "❌ Message must be less than 4000 characters. Note that "
                    "channel links add ~70 additional characters each."
                )
                await channel.send(embed=error_embed)
                return

            timestamp = datetime.now(timezone.utc)
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            files = []

            config = None
            if anon is not False:
                config = await self.bot.data_manager.get_or_load_config(guild.id)

            if anon is None:
                if config["anon"] == "true":
                    anon = True
                else:
                    anon = False

            dm_channel = None
            try:
                dm_channel = member.dm_channel or await member.create_dm()
            except Exception:
                error_embed.description = (
                    "❌ Unable to find DM channel with the ticket opener. "
                    "Please try again or close this ticket."
                )
                await channel.send(embed=error_embed)
                try:
                    member = await asyncio.wait_for(
                        guild.fetch_member(user_id), timeout=1
                    )
                    if member is not None:
                        await self.bot.cache.store_guild_member(guild.id, member)
                except Exception:
                    pass
                return
            if dm_channel is None:
                error_embed.description = (
                    "❌ Unable to find DM channel with the ticket opener. "
                    "Please close this ticket."
                )
                await channel.send(embed=error_embed)
                return

            # Process any attachments
            attachments = []
            final_attachments = []
            raw_files = []
            fileMessage = None
            file_embed = discord.Embed(
                title="",
                description="**Processing files...**\n"
                "Please note that image / video files may not send if they are too "
                "large (>10MB). For the fastest processing, upload large files to "
                "hosting websites and share links to the uploads instead.",
                color=discord.Color.blue(),
            )
            skipped_files = False
            if isinstance(message, discord.Message):
                attachments = message.attachments

                if len(attachments) > 0:
                    fileMessage = await channel.send(embed=file_embed)

                total_size = 0
                for file in attachments:
                    if file.size + total_size > MAX_FILE_SIZE:
                        skipped_files = True
                        continue
                    else:
                        final_attachments.append(file.url)
                    saved_file = io.BytesIO()
                    await file.save(saved_file)
                    raw_files.append(
                        (saved_file.getvalue(), file.filename)
                    )  # store raw bytes + filename
                    total_size += file.size

            if isinstance(message, discord.Message):
                await message.delete()

            if len(content) == 0 and len(final_attachments) == 0:
                empty_embed = discord.Embed(
                    description="❌ Message not sent, you cannot send an empty message.",
                    color=discord.Color.red(),
                )
                await channel.send(embed=empty_embed)
                return

            receipt_embed = discord.Embed(
                title=f"Message Sent [STAFF]",
                description=content,
                color=discord.Color.blue(),
            )
            receipt_embed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                receipt_embed.add_field(
                    name=f"Attachment {count}", value=url, inline=False
                )

            ap = None
            name = f"{author.name} | {author.id}"
            if anon:
                if config["aps"] == "true":
                    ap = await self.bot.data_manager.get_or_load_ap(guild.id, author.id)
                    if ap is not None:
                        name += " (Anonymous Profile)"
                    else:
                        name += " (Anonymous)"
                else:
                    name += " (Anonymous)"

            receipt_embed.set_author(
                name=name,
                icon_url=(author.avatar and author.avatar.url)
                or author.display_avatar.url,
            )

            if member:
                receipt_embed.set_footer(
                    text=f"{member.name} | {member.id}",
                    icon_url=(member.avatar and member.avatar.url)
                    or member.display_avatar.url,
                )
            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            sent_message = await channel.send(embed=receipt_embed, files=files)

            if skipped_files:
                skip_embed = discord.Embed(
                    description="⚠️ Some attachments were skipped for being too "
                    "large or exceeding the total file size limit (10MB).",
                    color=discord.Color.yellow(),
                )
                await channel.send(embed=skip_embed)

            if fileMessage is not None:
                await fileMessage.delete()

            send_embed = discord.Embed(
                title=f"Message Received",
                description=content,
                color=discord.Color.blue(),
            )
            send_embed.timestamp = datetime.now(timezone.utc)
            # Add attachment URLs to embed
            for count, url in enumerate(final_attachments, start=1):
                send_embed.add_field(
                    name=f"Attachment {count}", value=url, inline=False
                )

            if guild.icon:
                send_embed.set_footer(text=f"{guild.name}", icon_url=guild.icon.url)
            else:
                send_embed.set_footer(text=f"{guild.name}")

            if not anon:
                send_embed.set_author(
                    name=f"{author.name} | {author.id}",
                    icon_url=(author.avatar and author.avatar.url)
                    or author.display_avatar.url,
                )
            elif ap is not None:
                if ap["adj"] == "none":
                    ap["adj"] = ""
                send_embed.set_author(
                    name=f"{ap['adj']} {ap['noun']}", icon_url=ap["url"]
                )

            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            try:
                dm_message = await dm_channel.send(
                    embed=send_embed, files=files, view=MessageReceivedButton()
                )
            except Exception:
                error_embed.description = (
                    "❌ Unable to DM the ticket opener. Your last message was "
                    "**not** sent. **Please try again.** If this error persists, "
                    "they have their DMs closed or no longer share a server with "
                    "the bot."
                )
                await channel.send(embed=error_embed)
                try:
                    member = await asyncio.wait_for(
                        guild.fetch_member(user_id), timeout=1
                    )
                except Exception:
                    pass
                return

            files = [
                discord.File(io.BytesIO(data), filename=filename)
                for data, filename in raw_files
            ]
            try:
                thread_message = await thread.send(
                    embed=receipt_embed,
                    files=files,
                    allowed_mentions=discord.AllowedMentions(users=False),
                )
            except Exception as e:
                print("Thread send exception", e)
                pass

            await self.bot.data_manager.add_ticket_message(
                sent_message.id, None, channel.id, author.id, format_time, "Sent", True
            )
            await self.bot.channel_status.set_emoji(channel, "wait")
            await self.bot.data_manager.add_message_link(
                channel.id, sent_message.id, [dm_message.id, thread_message.id]
            )

        except Exception as e:
            if isinstance(message, discord.Message):
                await message.reply("❌ An error occurred, please try again")
            logger.exception(f"got_dm sent an error: {e}")

    async def store_comment(self, message: discord.Message):
        author = message.author
        channel = message.channel
        id_list = (channel.topic).split()
        thread_id = id_list[-1]

        thread = await self.bot.cache.get_channel(thread_id)
        content = None
        snapshot_flag = False

        if message.type.name == "FORWARD":
            snapshots = getattr(message, "message_snapshots", None)
            if snapshots:
                snapshot_flag = True
                snapshot = snapshots[0].message
                content = snapshot.content
            else:
                return
        else:
            content = message.content

        # Process any attachments
        attachments = []
        raw_files = []  # <-- store raw data

        if message:
            if snapshot_flag:
                attachments = message.message_snapshots[0].message.attachments
            else:
                attachments = message.attachments

            total_size = 0
            for file in attachments:
                if file.size + total_size > MAX_FILE_SIZE:
                    continue
                saved_file = io.BytesIO()
                await file.save(saved_file)
                raw_files.append(
                    (saved_file.getvalue(), file.filename)
                )  # store raw bytes + filename
                total_size += file.size

        files = [
            discord.File(io.BytesIO(data), filename=filename)
            for data, filename in raw_files
        ]
        thread_message = await thread.send(
            f"**{author.name}**\n{content}\n" f"-# `ID: {author.id}`",
            files=files,
            allowed_mentions=discord.AllowedMentions(users=False),
        )

        await self.bot.data_manager.add_message_link(
            channel.id, message.id, [-1, thread_message.id]
        )

    async def edit_comment(self, message):
        channel = message.channel
        author = message.author
        id_list = (channel.topic).split()
        thread_id = id_list[-1]

        thread = await self.bot.cache.get_channel(thread_id)

        _, thread_message_id = await self.bot.data_manager.get_linked_messages(
            channel.id, message.id
        )
        try:
            thread_message = await thread.fetch_message(thread_message_id)
        except Exception:
            pass
        if thread_message:
            await thread_message.edit(
                content=f"**{author.name}**\n{message.content}\n"
                f"-# `ID: {author.id}`"
            )
            return
        return None

    async def delete_comment(self, message):
        channel = message.channel
        id_list = (channel.topic).split()
        thread_id = id_list[-1]

        thread = await self.bot.cache.get_channel(thread_id)

        _, thread_message_id = await self.bot.data_manager.get_linked_messages(
            channel.id, message.id
        )
        try:
            thread_message = await thread.fetch_message(thread_message_id)
        except Exception:
            pass
        if thread_message:
            await thread_message.delete()
            return
        return None

    # Populate queue with unprocessed messages
    async def catch_modmail_backlog(self):
        for guild in self.bot.guilds:
            search_monitor = [
                (channel_id)
                for guild_id, channel_id, monitorType in self.bot.data_manager.monitored_channels
                if (guild_id == guild.id and monitorType == "Modmail log")
            ]

            if len(search_monitor) == 1:
                channel = guild.get_channel(int(search_monitor[0]))
                logger.log(
                    "SYSTEM", f"Scanning channel: {channel.name} in {guild.name}"
                )
                try:
                    async for message in channel.history(
                        limit=None, oldest_first=False
                    ):
                        if not self.has_mantis_reaction(message):
                            if message.author.id == 575252669443211264:
                                await self.processing_queue.put(message)
                        else:
                            # Stop scanning this channel after finding the first processed message
                            break
                except Exception as e:
                    logger.error(
                        f"Error fetching history in channel {channel.name}: {e}"
                    )

    # Check if the message has a Mantis reaction
    def has_mantis_reaction(self, message: discord.Message) -> bool:
        for reaction in message.reactions:
            if (reaction.emoji.id == 1304887716370186330) or (
                reaction.emoji == "<:mantis:1304887716370186330>"
            ):
                return True
        return False

    # Process all messages in the queue
    async def process_queue(self):
        # Drain the queue into a list
        items = []
        while not self.processing_queue.empty():
            items.append(await self.processing_queue.get())

        # Process items in reverse order, needed for later logic
        items.reverse()
        for message in items:
            try:
                await self.process_modmail(message, True)
            except Exception as e:
                logger.error(f"Error processing message {message.id}: {e}")
            finally:
                self.processing_queue.task_done()

    # Handles all potential Modmail ticket creation events
    async def process_modmail(
        self, message: discord.Message, is_catchup: bool, term=None
    ):
        embed = message.embeds[0]
        title = embed.title

        if is_catchup:
            if title == "New Ticket":
                await self.log_open_ticket(message, "bad")
            if title == "Ticket Closed":
                await self.log_closed_ticket(message, None)
        else:
            if title == "New Ticket":
                await self.log_open_ticket(message, "good")

            if title == "Ticket Closed":
                await message.add_reaction(emojis.mantis)

    # Stores opened Modmail tickets into the DB
    # Adds ticket to Redis cache if the ticket is still open
    async def log_open_ticket(self, message: discord.Message, status: str):
        try:
            guild = message.guild
            this_channel = message.channel
            this_channel_id = this_channel.id
            embed = message.embeds[0]
            footer = embed.footer.text
            open_id = (footer.split())[-1]
            open_name = ((footer.split())[0])[:-2]
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            # Check if associated ticket channel exists for 2 seconds, if not assume ticket has already closed
            ticket_channel = None
            start_time = time.time()
            while (time.time() - start_time < 2) and (ticket_channel is None):
                for channel in guild.channels:
                    if (open_name).replace("_", "").replace(".", "") in channel.name:
                        ticket_channel = channel
                await asyncio.sleep(0.1)

            if ticket_channel is not None:
                ticket_channel_id = ticket_channel.id
                ticket_channel_timestamp = ticket_channel.created_at

                # Check that found channel shares creation time (within one minute), if not assume this channel belongs to a different ticket
                difference = abs((timestamp - ticket_channel_timestamp).total_seconds())
                if difference <= 60:
                    await self.bot.data_manager.add_ticket(
                        ticket_channel_id, message.id
                    )
                    await self.bot.channel_status.set_emoji(ticket_channel, "new")

                else:
                    logger.debug(
                        f"Attempted to match incorrect channel ({ticket_channel_id}) "
                        "to modmail log 'New Ticket' message, ticket must have already "
                        "closed"
                    )
                    pass
            else:
                logger.debug("Ticket channel is already closed")
                pass

            game_type = SERVER_TO_GAME.get(guild.id, None)
            roblox_data = None

            if game_type:
                roblox_data = await get_roblox_data(game_type, guild.id, open_id)

            priority_values = roblox_data[2:] if roblox_data else []

            query = f"""
                INSERT IGNORE INTO tickets VALUES
                ({message.id},
                {guild.id},
                {this_channel_id},
                '{format_time}',
                NULL,
                {open_id},
                NULL,
                NULL,
                'open',
                '{status}',
                'false',
                1,
                {priority_values[0]},
                {priority_values[1]});
                """
            await self.bot.data_manager.execute_query(query, False)
            await message.add_reaction(emojis.mantis)

            if status == "good":
                pass
            else:
                logger.warning(
                    f"*** Processed open modmail ticket (Message ID: {message.id}) BAD DATA ***"
                )

        except Exception as e:
            logger.exception(f"Error processing new or caught modmail ticket: {e}")

    # Updates Modmail tickets as closed in the DB
    # Removes the ticket from the Redis cache if the ticket was still registered as open
    async def log_closed_ticket(self, message: discord.Message, modmail_message_id):
        try:
            err = False
            guild = message.guild
            this_channel_id = message.channel.id
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            if modmail_message_id is None:
                embed = message.embeds[0]
                footer = embed.footer.text
                open_id = (footer.split())[-1]
                author_name = (embed.author.name).split()
                closeName = author_name[0][:-2]
                close_id = self.bot.data_manager.mod_ids.get(closeName, None)

                query = f"""
                    SELECT message_id FROM tickets WHERE
                    (guild_id = {guild.id}) AND
                    (openByID = {open_id}) AND
                    (status = 'open')
                    ORDER BY dateOpen Asc;
                    """
                result = await self.bot.data_manager.execute_query(query)

                # Check if results returned anything, if so select the oldest open ticket to associate the close with
                if len(result) != 0:
                    modmail_message_id = result[0][0]
                    if len(result) == 1:
                        logger.debug("Found one matching log in DB for a closed ticket")
                    else:
                        logger.debug(
                            "Found two or more matching open logs in DB, selected the oldest one"
                        )
                else:
                    logger.error(
                        f"Could not find open compliment to close embed {message.id}, sent on {format_time}"
                    )
                    err = True

                # Update ticket at modmail_message_id
                if not err and close_id:
                    query = f"""
                        UPDATE tickets SET
                        dateClose = '{format_time}',
                        closeByID = {close_id},
                        closeByUN = '{closeName}',
                        status = 'closed',
                        flag = 'bad' WHERE (message_id = {modmail_message_id});
                        """
                    await self.bot.data_manager.execute_query(query, False)

                    # Remove from Redis if ticket is still present
                    await self.bot.data_manager.remove_ticket_modmail(
                        modmail_message_id
                    )
                    logger.warning(
                        f"*** Processed closed modmail ticket (Message ID: {modmail_message_id}) BAD DATA ***"
                    )
                    #

                else:
                    logger.error(f"Close embed not loggable")
                    await message.add_reaction(emojis.mantis)

            else:
                close_id = message.author.id
                closeName = message.author.name
                query = f"""
                    UPDATE tickets SET
                    dateClose = '{format_time}',
                    closeByID = {close_id},
                    closeByUN = '{closeName}',
                    status = 'closed' WHERE (message_id = {modmail_message_id});
                    """
                await self.bot.data_manager.execute_query(query, False)

                # Remove from Redis
                await self.bot.data_manager.remove_ticket(this_channel_id)

        except Exception as e:
            logger.error(f"Error closing modmail ticket: {e}")

    # On-message event listener for messages in #modmail-log channels or modmail categories
    @commands.Cog.listener()
    async def on_message(self, message):
        # Temp, allows Mantid to still work (allows Modmail message processing)
        if message.author.bot and message.author.id != 575252669443211264:
            return

        # Process valid commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if isinstance(message.channel, discord.DMChannel):
            limited, retry, was_notified = self.bot.queue.check_user_action_cooldown(
                "dm_start", message.author.id
            )

            if limited:
                if not was_notified:
                    self.bot.queue.user_action_cooldowns["dm_start"]["notified"][
                        message.author.id
                    ] = True
                    error_embed = discord.Embed(
                        description=f"❌ You're messaging me too quickly — retry in {retry:.1f} seconds.",
                        color=discord.Color.red(),
                    )
                    await message.channel.send(embed=error_embed)
                return

            await self.bot_dm(message)
            return

        this_channel = message.channel
        this_channel_id = this_channel.id
        this_channel_cat_id = message.channel.category_id

        # check if chanel descrip is good, if so send mod message to dm
        # check permissions
        if isinstance(this_channel, discord.TextChannel):
            if this_channel.topic:
                if "Ticket channel" in this_channel.topic:
                    author = message.author
                    id_list = (this_channel.topic).split()
                    thread_id = id_list[-1]
                    user_id = id_list[-2]

                    if message.content.startswith("+"):
                        asyncio.create_task(
                            self.route_to_dm(
                                message,
                                this_channel,
                                author,
                                thread_id,
                                user_id,
                                None,
                                False,
                            )
                        )
                        return

                    else:
                        # Process comment
                        timestamp = datetime.now(timezone.utc)
                        format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        await self.bot.data_manager.add_ticket_message(
                            message.id,
                            None,
                            this_channel_id,
                            message.author.id,
                            format_time,
                            "Discussion",
                            True,
                        )
                        asyncio.create_task(self.store_comment(message))
                        return

        search_monitor = [
            (channel_id, monitorType)
            for guild_id, channel_id, monitorType in self.bot.data_manager.monitored_channels
            if (channel_id == this_channel_id or channel_id == this_channel_cat_id)
        ]

        if len(search_monitor) == 0:
            return

        elif len(search_monitor) == 1:
            channel = message.channel
            message_id = message.id
            guild = message.guild
            this_author_id = message.author.id
            this_authorName = message.author.name
            timestamp = message.created_at
            format_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            monitor_type = ""
            monitor_type = search_monitor[0][1]

            # Check if channel is a Modmail log
            if monitor_type == "Modmail log":
                if this_author_id == 575252669443211264:
                    if message.embeds:
                        await self.process_modmail(message, False)

            # Check if channel is in a tickets or overflow category
            if (
                monitor_type == "Tickets category"
                or monitor_type == "Overflow category"
            ):

                # Check if channel is cached as a ticket
                modmail_message_id = await self.bot.data_manager.get_ticket(
                    this_channel_id
                )
                if modmail_message_id is not None:
                    if this_author_id == 575252669443211264:
                        if message.embeds:
                            embed = message.embeds[0]

                            # Store received message (embed by Modmail bot from DM)
                            if embed.title == "Message Received":
                                footer = embed.footer.text
                                author_id = (footer.split())[-1]
                                await self.bot.data_manager.add_ticket_message(
                                    message_id,
                                    modmail_message_id,
                                    this_channel_id,
                                    author_id,
                                    format_time,
                                    "Received",
                                )
                                await self.bot.channel_status.set_emoji(
                                    channel, "alert"
                                )

                            # Store sent message (embed from the Modmail bot to DM)
                            elif embed.title == "Message Sent":
                                author_name = (embed.author.name).split()
                                author_username = (author_name[0])[:-2]
                                author_id = self.bot.data_manager.mod_ids.get(
                                    author_username, None
                                )
                                # FIXME fix this soon, but not rn, issue with stored moderator IDs
                                if author_id is not None:
                                    await self.bot.data_manager.add_ticket_message(
                                        message_id,
                                        modmail_message_id,
                                        this_channel_id,
                                        author_id,
                                        format_time,
                                        "Sent",
                                    )
                                await self.bot.channel_status.set_emoji(channel, "wait")

                            else:
                                pass
                                # Title has to be Message Received or Message Sent
                    else:
                        # Chatting message, message to be sent by Modmail, OR =close
                        if message.content.startswith("="):
                            # Chatting message or =close
                            if message.content.startswith(("=c", "=ac")):
                                self.bot.data_manager.mod_ids[this_authorName] = (
                                    this_author_id
                                )

                                await self.log_closed_ticket(
                                    message, modmail_message_id
                                )
                                # None argument indicates deleting channel from status queue
                                await self.bot.channel_status.set_emoji(channel, None)

                            elif message.content.startswith(
                                (
                                    "=r ",
                                    "=reply ",
                                    "=ar ",
                                    "=areply ",
                                    "=air",
                                    "=aireply",
                                    "=s ",
                                    "=snippet ",
                                    "=as ",
                                    "=asnippet ",
                                )
                            ):
                                self.bot.data_manager.mod_ids[this_authorName] = (
                                    this_author_id
                                )

                            else:
                                # Store chatting message, label it as such
                                await self.bot.data_manager.add_ticket_message(
                                    message_id,
                                    modmail_message_id,
                                    this_channel_id,
                                    this_author_id,
                                    format_time,
                                    "Discussion",
                                )
                        else:
                            # Message to be sent by Modmail
                            self.bot.data_manager.mod_ids[this_authorName] = (
                                this_author_id
                            )
                else:
                    pass
        else:
            # Calls if message is from the Modmail bot in a #modmail-log channel
            if message.author.id == 575252669443211264:
                if message.embeds:
                    await self.process_modmail(message, False)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # Ignore bot edits to prevent loops
        if before.author.bot:
            return

        if before.content == after.content:
            return

        if isinstance(before.channel, discord.TextChannel):
            if before.channel.topic:
                if "Ticket channel" in before.channel.topic:
                    await self.edit_comment(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        # Ignore bot message deletions
        if message.author.bot:
            return

        if isinstance(message.channel, discord.TextChannel):
            if message.channel.topic:
                if "Ticket channel" in message.channel.topic:
                    if not (message.content.startswith("+")):
                        await self.delete_comment(message)


async def setup(bot):
    await bot.add_cog(Analytics(bot))
