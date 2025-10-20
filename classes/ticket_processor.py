import asyncio
import json
from collections import namedtuple

import discord

from classes.helpers import *
from classes.embeds import Embeds
from classes.paginator import Paginator
from utils.logger import logger


class TicketQueue:
    def __init__(self, bot):
        self.bot = bot
        self.queue_worker_task = None
        self.update_interval = 5  # seconds
        self.prior_queues = {}
        self.queue_channels = {}
        self.queue_messages = {}

    async def start_worker(self):
        try:
            self.queue_worker_task = asyncio.create_task(self._queue_watcher())
            logger.success("Ticket queue worker started")
        except Exception as e:
            logger.error(f"Failed to start queue worker: {e}")

    async def stop_worker(self):
        try:
            self.queue_worker_task.cancel()
            logger.success("Ticket queue worker shut down")
        except Exception as e:
            logger.error(f"Failed to stop queue worker: {e}")

    async def _add_ticket(self, ticket: Ticket, info_message: discord.Message):
        ticket.dm_message_id = info_message.id
        await self.bot.cache.store_message(info_message)
        await self.bot.data_manager.add_ticket_back_queue(ticket)

    async def _get_next_ticket(self, guild_id: int) -> Ticket | None:
        return await self.bot.data_manager.pop_oldest_ticket(guild_id)

    async def _move_ticket_to_front(self, guild_id: int, user_id: int):
        ticket = await self.bot.data_manager.remove_ticket_from_queue(guild_id, user_id)
        if ticket:
            await self.bot.data_manager.add_ticket_front_queue(ticket)

    async def _edit_info_message(self, ticket: Ticket):
        try:
            user = await self.bot.cache.get_user(ticket.user_id)
            dm_channel = user.dm_channel or await user.create_dm()
            if dm_channel:
                info_message = await self.bot.cache.get_message(
                    dm_channel, ticket.dm_message_id
                )
                if info_message:
                    error_embed = Embeds.error(
                        description="Thank you for reaching out to the moderation team!\n\n"
                        f"Unfortunately, tickets of type **{ticket.type_name}** have "
                        "reached maximum capacity. Please try again later for an "
                        "opening, we thank you in advance for your patience.",
                    )
                    await info_message.edit(embed=error_embed)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error editing info message for ticket {ticket}: {e}")
            return False

    # open tickets if there's space
    # these tickets get removed from thew queue = live update
    # for tickets that stay in the queue, the queue needs updated with their status?
    # or, we find a way to avoid needing this update, and pass the fetched queue onwards for further processing
    # New tickets then are only considered after the full processing loop (should be a couple seconds at most?)
    # Actual ticket opening can take longer of course

    async def _try_open_tickets(self):
        """Attempts to open tickets if there's space."""
        full_categories = []
        queues = await self.bot.data_manager.get_all_queues()
        if queues:
            print(queues)
        for guild_id, queue in queues.items():
            for ticket in queue:
                category_id = ticket.category_id
                if category_id in full_categories:
                    # TODO if queueing is off, send full message
                    state = await self._edit_info_message(ticket)
                    if state:
                        await self.bot.data_manager.remove_ticket_from_queue(
                            ticket.guild_id, ticket.user_id
                        )
                    continue
                category = await self.bot.cache.get_channel(ticket.category_id)
                if len(category.channels) >= 50:
                    full_categories.append(category.id)
                    # TODO if queueing is off, send full message
                    state = await self._edit_info_message(ticket)
                    if state:
                        await self.bot.data_manager.remove_ticket_from_queue(
                            ticket.guild_id, ticket.user_id
                        )
                    continue
                try:
                    asyncio.create_task(self.bot.opener.open_ticket(ticket))
                    await self.bot.data_manager.remove_ticket_from_queue(
                        ticket.guild_id, ticket.user_id
                    )
                except Exception as e:
                    logger.exception(
                        f"Error opening ticket for user {ticket.user_id}: {e}"
                    )
        return queues

    async def queue_embed_template(self, guild, type_name):
        footer_text = (
            'Want to leave the queue? Hit "**Leave Queue**" to delete '
            "your pending ticket. You'll have to make a new one if you do."
        )

        embed = Embeds.info(
            title="You're in Queue",
            description=f"{guild.name} is currently at max capacity for "
            f"tickets of type: {type_name}.\n\nDon't worry! Your submitted information "
            "has been **saved** and your ticket is currently in the **ticket queue**. "
            "Once room is available in the server, your ticket will automatically open.",
        )
        embed.set_footer(text=footer_text)
        return embed

    async def _build_paginated_embeds(self, queue, per_page=10):
        pages = []
        if not queue:
            embed = Embeds.info(
                title="Ticket Queue", description="No tickets are currently waiting."
            )
            return [embed]

        for i in range(0, len(queue), per_page):
            chunk = queue[i : i + per_page]
            embed = Embeds.info(
                title="Pending Ticket Queue",
                description=f"Total queued: **{len(queue)}**",
            )
            for index, ticket in enumerate(chunk, start=i + 1):
                user_mention = f"<@{ticket.user_id}>"
                hours_played = (
                    "N/A" if ticket.hours_played == -1 else f"{ticket.hours_played}"
                )
                robux_spent = (
                    "N/A" if ticket.robux_spent == -1 else f"{ticket.robux_spent}"
                )
                embed.add_field(
                    name=f"{index}. {ticket.type_name}",
                    value=f"Opener: {user_mention}\n"
                    f"Metrics: **{robux_spent}** R$ **{hours_played}** Hrs\n"
                    f"Submitted: <t:{ticket.submitted_at}:D> (<t:{ticket.submitted_at}:R>)\n",
                    inline=False,
                )
            pages.append(embed)

        pages = add_footers(pages)
        return pages

    async def _is_queue_embed(self, message: discord.Message):
        """Check if a message is a queue embed."""
        if not message.embeds:
            return False
        embed = message.embeds[0]
        if embed.title and "Ticket Queue" in embed.title:
            return True
        return False

    async def _get_queue_channel(self, guild_id: int):
        queue_channel_id = self.queue_channels.get(guild_id, None)
        if not queue_channel_id:
            config = await self.bot.data_manager.get_or_load_config(guild_id)
            queue_channel_id = config["responses_id"]
            self.queue_channels[guild_id] = queue_channel_id

        queue_channel = await self.bot.cache.get_channel(queue_channel_id)
        return queue_channel

    async def _get_queue_message(self, guild_id: int, queue_channel):
        queue_message = None
        queue_message_id = self.queue_messages.get(guild_id, None)
        if not queue_message_id:
            async for message in queue_channel.history(limit=1):
                if await self._is_queue_embed(message):
                    queue_message = message
                    self.queue_messages[guild_id] = queue_message.id

        return queue_message

    async def _update_server_embeds(self, queues):
        setup_guilds = []
        for guild in self.bot.guilds:
            config = await self.bot.data_manager.get_or_load_config(guild.id)
            if not config:
                continue
            setup_guilds.append(guild)

        for guild in setup_guilds:
            queue = queues.get(guild.id, [])
            prior_queue = self.prior_queues.get(guild.id, [])

            if queue != prior_queue:
                self.prior_queues[guild.id] = queue.copy()

                pages = await self._build_paginated_embeds(queue)
                view = Paginator(pages, timeout=None)

                queue_channel = await self._get_queue_channel(guild.id)
                queue_message = await self._get_queue_message(guild.id, queue_channel)
                if queue_message:
                    await queue_message.edit(embed=pages[0], view=view)
                    view.message = queue_message
                else:
                    queue_message = await queue_channel.send(embed=pages[0], view=view)
                    view.message = queue_message

    # no longer updating DM embeds like this, just supplying update info via a button
    # does a direct redis call, checks there for position when button is pressed
    # will update embed on press

    async def _queue_watcher(self):
        while True:
            try:
                queues = await self._try_open_tickets()
                # await self._update_server_embeds(queues)

            except Exception as e:
                print(f"[QueueWatcher] Error: {e}")
            await asyncio.sleep(self.update_interval)
