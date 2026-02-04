import asyncio
import time

import discord
import emoji

from cogs.tickets import close_ticket
from utils import emojis
from utils.logger import *


class ChannelStatus:
    def __init__(self, bot):
        self.bot = bot
        self.last_update_times = {}  # Stores only the latest update per channel
        self.pending_updates = {}  # Stores text newname
        self.cooldown = 303  # 1 update per ~5 minutes
        self.channel_status_worker_task = None
        self.timer_worker_task = None
        self.timers = {}  # Stores ticket close timers

    async def start_worker(self):
        try:
            self.channel_status_worker_task = asyncio.create_task(
                self.channel_status_worker()
            )
            self.timer_worker_task = asyncio.create_task(self.timer_worker())
            logger.success("Workers started")

        except Exception as e:
            logger.error(f"Error starting workers: {e}")

    async def stop_worker(self):
        try:
            self.channel_status_worker_task.cancel()
            self.timer_worker_task.cancel()
            logger.success("Channel workers shut down")

        except Exception as e:
            logger.exception(f"Error shutting down workers: {e}")

    async def _collect_channel_updates(self):
        try:
            now = int(time.time())
            channels_to_update = []
            for channel_id, new_name in list(self.pending_updates.items()):
                last_update_time = self.last_update_times.get(channel_id, None)

                if not last_update_time:
                    last_update_time = now
                    self.last_update_times[channel_id] = now

                if (now - last_update_time) >= self.cooldown:
                    channels_to_update.append((channel_id, new_name))

            return channels_to_update
        except Exception as e:
            logger.exception(f"Error collecting channel updates: {e}")
            return []

    async def _apply_channel_updates(self, channels_to_update):
        for channel_id, new_name in channels_to_update:
            channel = await self.bot.cache.get_channel(channel_id)
            pop_flag = True
            try:
                if channel:
                    try:
                        await asyncio.wait_for(channel.edit(name=new_name), timeout=1)
                    except asyncio.TimeoutError:
                        logger.error(
                            f"Status update timed out for channel "
                            f"{channel.name} ({channel_id})"
                        )
                        pop_flag = False
                    except discord.NotFound:
                        logger.error(
                            f"Channel not found for update "
                            f"{channel.name} ({channel_id})"
                        )
                    except Exception as e:
                        logger.error(
                            f"Status update errored for channel "
                            f"{channel.name} ({channel_id}): {e}"
                        )
                        pop_flag = False
                self.last_update_times[channel_id] = int(time.time())

            except Exception as e:
                logger.error(f"Failed to update channel {channel.id}: {e}")

            if pop_flag:
                self.pending_updates.pop(channel_id, None)
            await asyncio.sleep(0.5)

    # Worker, attempts to edit a channel's name in the queue after 5 minutes
    # Cooldown is local to each channel, set by Discord's ratelimiting
    async def channel_status_worker(self):
        while True:
            try:
                await asyncio.sleep(20)
                channels_to_update = await self._collect_channel_updates()

                if channels_to_update:
                    await self._apply_channel_updates(channels_to_update)

            except Exception as e:
                logger.exception(f"Channel worker sent an error: {e}")

    async def _collect_expired_timers(self):
        now = int(time.time())
        expired_timers = []

        for channel_id, fields in self.timers.items():
            end_time, mod_id, opener_id, reason = fields
            if now >= int(end_time):
                expired_timers.append((channel_id, mod_id, opener_id, reason))

        return expired_timers

    # Timer worker, handles scheduled name changes
    async def timer_worker(self):
        while True:
            try:
                await asyncio.sleep(60)

                expired_timers = await self._collect_expired_timers()
                for channel_id, mod_id, opener_id, reason in expired_timers:

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        try:
                            channel = await asyncio.wait_for(
                                self.bot.fetch_channel(channel_id), timeout=1
                            )
                        except discord.NotFound:
                            # TODO Mark as closed
                            # Remove ticket from database
                            pass
                        except Exception:
                            pass

                    if channel:
                        try:
                            guild = channel.guild
                            mod = await self.bot.cache.get_guild_member(guild, mod_id)
                            await close_ticket(
                                self.bot,
                                channel,
                                mod,
                                opener_id,
                                guild.id,
                                reason,
                                None,
                                True,
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed to update channel "
                                f"{channel.id} after timer expired: {e}"
                            )

                    self.timers.pop(channel_id, None)
                    await self.bot.data_manager.save_timers_to_redis()
                    await asyncio.sleep(2)

            except Exception:
                await asyncio.sleep(5)

    # Queues a channel name update, replacing any previous updates for that channel
    def queue_update(
        self,
        channel: discord.TextChannel,
        new_emoji_str: str,
        new_name: str,
        manual: bool,
    ) -> bool:
        try:
            if new_emoji_str is None:
                self.pending_updates.pop(channel.id, None)
                return False

            # If update is the same as current or pending name, drop
            pending_name = self.pending_updates.get(channel.id, channel.name)
            if pending_name == new_name:
                return False

            current_emoji_str = next(
                (
                    emoji
                    for emoji, value in emojis.emoji_map.items()
                    if value[0] == pending_name[0]
                ),
                None,
            )

            restricted_updates = {"new": "alert", "inactive": "wait"}
            # Check for restricted automatic updates
            if not manual:
                if current_emoji_str:
                    restriction = restricted_updates.get(current_emoji_str, None)
                    if new_emoji_str == restriction:
                        return False

                    # If current name is permanent, drop new name
                    if emojis.emoji_map.get(current_emoji_str)[1]:
                        return False

                    # Delete timer if switching from inactive to alert
                    if current_emoji_str == "inactive" and new_emoji_str == "alert":
                        self.timers.pop(channel.id, None)

            # Queue the update
            self.pending_updates[channel.id] = new_name
            return True

        except Exception as e:
            logger.exception(f"queue_update sent an error: {e}")
            return False

    # normal emoji changes are FALSE for manual and have NONE for nsfw_state
    # nsfw_state changes are TRUE for manual and have TRUE/FALSE for nsfw_state
    # inactive / other perm emojis are TRUE for manual and have NONE for nsfw_state

    # the inactive emojis specifically cant be overwritten unless by a non-manual wait

    # Set emoji at the start of a channel's name
    async def set_emoji(
        self,
        channel: discord.TextChannel,
        emoji_str: str,
        manual: bool = False,
        nsfw_state: bool = None,
    ) -> bool:
        new_name = ""

        if nsfw_state is not None:
            current_name = self.pending_updates.get(channel.id, channel.name)

            if nsfw_state:
                new_name = (
                    f"{(current_name)[0]}"
                    f"{(emojis.emoji_map.get('nsfw'))[0]}"
                    f"{(current_name)[1:]}"
                )
            elif not nsfw_state:
                new_name = f"{(current_name)[0]}{(current_name)[2:]}"

        else:
            if emoji_str is None:
                self.queue_update(channel, emoji_str, None, manual)
                return True

            selected_emoji = (emojis.emoji_map.get(emoji_str))[0]
            # Remove prefixed emoji if there is one
            if (channel.name)[0] in emoji.EMOJI_DATA and (
                not channel.name.startswith((emojis.emoji_map.get("nsfw"))[0])
            ):
                new_name = f"{selected_emoji}{(channel.name)[1:]}"
            else:
                new_name = f"{selected_emoji}{channel.name}"

        return self.queue_update(channel, emoji_str, new_name, manual)

    # Check if the input is a valid Unicode emoji
    def check_unicode(self, input_emoji: str) -> bool:
        return input_emoji in emoji.EMOJI_DATA

    async def add_timer(self, channel_id, time, mod_id, opener_id, reason):
        self.timers[channel_id] = [time, mod_id, opener_id, reason]
        await self.bot.data_manager.save_timers_to_redis()

    async def remove_timer(self, channel_id):
        if self.timers.pop(channel_id, None) is not None:
            await self.bot.data_manager.save_timers_to_redis()
            return True
        return False

    def get_timer(self, channel_id):
        timer = self.timers.get(channel_id, None)
        return timer
