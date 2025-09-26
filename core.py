import os

import discord
from classes.cache import Cache
from classes.channel_status import ChannelStatus
from classes.data_manager import DataManager
from classes.helpers import Helper
from classes.rate_limiter import Queue
from classes.ticket_opener import TicketOpener
from classes.ticket_submitter import DMCategoryButtonView, TicketRatingView
from discord.ext import commands, tasks
from utils.logger import *


class MailBee(commands.Bot):
    """
    A Discord bot built from the Discord.py library.

    MailBee is a ModMail-style ticketing bot designed to facilitate communication
    between server staff and members via the privacy of direct messages. MailBee relies
    on the Discord Modal feature to gather user input before creating a standard
    ModMail channel.

    Data storage is handled as follows:
    - MySQL v8+ for persistent data storage.
    - Valkyrie (Redis) for caching and fast access to frequently used data.
    - In-memory storage for short TTL data.

    Attributes:
        data_manager (DataManager): Manages data-related operations.
        channel_status (ChannelStatus): Tracks the status of channels.
        helper (Helper): Provides helper functions for the bot.
        cache (Cache): Caches data for quick access.
        opener (TicketOpener): Handles ticket opening functionalities.
        queue (Queue): Manages queued API calls.
        api_patched (bool): Indicates whether the API routes have been patched.
        patch_api_routes(queue): Patches the API routes to use the Queue class.
        on_ready(): Called when the bot is ready and connected to Discord.
        close(): Shuts down the database, redis, and workers before bot shutdown.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.dm_messages = True
        intents.message_content = True
        description = "MailBee: A ticketing and analytics system for Discord"

        # Create bot instance with command prefix
        super().__init__(
            command_prefix=commands.when_mentioned_or("+"),
            intents=intents,
            description=description,
            case_insensitive=True,
            help_command=None,
        )
        self.data_manager = DataManager(self)
        self.channel_status = ChannelStatus(self)
        self.helper = Helper(self)
        self.cache = Cache(self)
        self.opener = TicketOpener(self)
        self.queue = Queue()

        self.heartbeat = tasks.loop(minutes=10)(self._heartbeat)

    # Monkey-patch discord.py http calls to use the Queue class
    def _patch_api_routes(self, queue) -> None:

        # Save originals
        global original_send, original_edit, original_delete, original_add_reaction
        global original_fetch_message

        original_send = discord.abc.Messageable.send
        original_edit = discord.Message.edit
        original_delete = discord.Message.delete
        original_fetch_message = discord.TextChannel.fetch_message
        original_add_reaction = discord.Message.add_reaction
        original_webhook_send = discord.webhook.async_.Webhook.send

        # Monkey patch
        async def queued_send(self_, *args, **kwargs):
            return await queue.call(
                original_send, self_, *args, **kwargs, route_type="message_send"
            )

        async def queued_edit(self_, *args, **kwargs):
            return await queue.call(
                original_edit, self_, *args, **kwargs, route_type="message_edit"
            )

        async def queued_delete(self_, *args, **kwargs):
            return await queue.call(
                original_delete, self_, *args, **kwargs, route_type="message_delete"
            )

        async def queued_fetch_message(self_, message_id, *args, **kwargs):
            return await queue.call(
                original_fetch_message,
                self_,
                message_id,
                *args,
                **kwargs,
                route_type="fetch_message",
            )

        async def queued_add_reaction(self_, emoji, *args, **kwargs):
            return await queue.call(
                original_add_reaction,
                self_,
                emoji,
                *args,
                **kwargs,
                route_type="add_reaction",
            )

        async def queued_webhook_send(self_, *args, **kwargs):
            return await queue.call(
                original_webhook_send,
                self_,
                *args,
                **kwargs,
                route_type="followup_send",
            )

        # Apply patches
        discord.abc.Messageable.send = queued_send
        discord.Message.edit = queued_edit
        discord.Message.delete = queued_delete
        discord.TextChannel.fetch_message = queued_fetch_message
        discord.Message.add_reaction = queued_add_reaction
        discord.webhook.async_.Webhook.send = queued_webhook_send

    async def _connect_to_datasources(self) -> None:
        if not self.data_manager.db_pool:
            try:
                await self.data_manager.connect_to_db()
            except Exception as e:
                logger.critical(f"All database re-connect attempts failed: {e}")
                raise Exception("Data connections failed")

        if self.data_manager.db_pool:
            await self.data_manager.data_startup()

    async def _load_cogs(self) -> None:
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                if (f"cogs.{filename[:-3]}") in self.extensions:
                    logger.info(f"Already loaded cog: {filename}")

                else:
                    try:
                        await self.load_extension(f"cogs.{filename[:-3]}")
                        logger.success(f"Loaded cog: {filename}")
                    except Exception as e:
                        logger.exception(f"Failed to load {filename}: {e}")
                        raise Exception("Cog loading failed")

    async def _quit(self, reason) -> None:
        logger.critical(f"------- STARTUP FAILED: {reason} -------")
        await self.close()

    async def on_ready(self):
        logger.log("SYSTEM", "------- STARTUP INITIATED ----------------")

        try:
            logger.log("SYSTEM", "------- FETCHING DATA --------------------")
            await self._connect_to_datasources()

            logger.log("SYSTEM", "------- LOADING COGS ---------------------")
            await self._load_cogs()

        except Exception as e:
            await self._quit(e)
            return

        logger.log("SYSTEM", "------- ADDING PERSISTENT VIEWS ----------")
        self.add_view(DMCategoryButtonView(self))
        self.add_view(TicketRatingView(self))

        logger.log("SYSTEM", "------- STARTUP COMPLETE -----------------")
        activity_type = discord.ActivityType.watching
        activity_str = "for tickets!"
        await self.change_presence(
            activity=discord.Activity(type=activity_type, name=activity_str)
        )

        logger.log("SYSTEM", f"MailBee is ready! Logged in as {self.user}")

    async def _heartbeat(self):
        await self.data_manager.save_status_dicts_to_redis()
        await self.data_manager.save_timers_to_redis()

        status = await self.data_manager.check_db_health()
        if not status:
            if not self.data_manager.db_pool:
                await self.data_manager.connect_to_db()

    # Shuts down database, redis, and workers before bot shutdown
    async def close(self):
        logger.log("SYSTEM", "------- SHUTTING DOWN --------------------")
        if self.heartbeat.is_running():
            self.heartbeat.cancel()
        await self.data_manager.data_shutdown()
        await super().close()
