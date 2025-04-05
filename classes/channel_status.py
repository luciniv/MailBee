import discord
import asyncio
import emoji
from utils import emojis
from datetime import datetime, timezone, timedelta
import time
from utils.logger import *


# logger.debug = lambda *a, **kw: None  # No-op debug logging
MAX_RETRIES = 3


class ChannelStatus:
    def __init__(self, bot):
        self.bot = bot
        self.last_update_times = {}  # Stores only the latest update per channel
        self.pending_updates = {}  # Stores text newname 
        self.cooldown = 300  # 1 update per 5 minutes
        self.worker_task = None
        self.timer_worker_task = None
        self.timers = {}  # Stores ticket close timers


    # Start worker 
    async def start_worker(self):
        try:
            self.worker_task = asyncio.create_task(self.worker())
            self.timer_worker_task = asyncio.create_task(self.timer_worker())
            logger.success("Workers started")
        except Exception as e:
            logger.error(f"Error starting workers: {e}")


    # Shutdown worker gracefully
    async def shutdown(self):
        try:
            self.worker_task.cancel()
            self.timer_worker_task.cancel()
            logger.success("Workers shut down")

        except Exception as e:
            logger.exception(f"Error shutting down workers: {e}")


    # Worker, attempts to edit a channel's name in the queue after 5 minutes
    # Cooldown is local to each channel, set by Discord's ratelimiting (oh well, what can one do)
    async def worker(self): 
        while True:
            await asyncio.sleep(20)  # Prevents high CPU usage
            now = int(time.time())
            channels_to_update = []

            # Collect channels that are ready to be updated
            print("start of loop")
            for channel_id, new_name in list(self.pending_updates.items()):

                last_update_time = self.last_update_times.get(channel_id, None)
                if (last_update_time is None):
                    if (new_name.startswith(emojis.emoji_map.get("new", ""))):
                        last_update_time = now - self.cooldown
                    else:
                        last_update_time = now
                        self.last_update_times[channel_id] = now

                if (now - last_update_time) >= self.cooldown:
                    channels_to_update.append((channel_id, new_name))

            print("got ready updates", channels_to_update)
            # Apply updates for ready channels
            for channel_id, new_name in channels_to_update:
                print("Started process to update channel")
                print("getting channel", channel_id)
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel is None:
                        print("Channel not cached, attempting fetch")
                        channel = await asyncio.wait_for(self.bot.fetch_channel(channel_id), timeout=2)
                except asyncio.TimeoutError:
                    print("timeout error")
                    
                except discord.NotFound:
                    print(f"Channel {channel_id} was deleted")
                    
                except Exception as e:
                    print(f"Fetching channel {channel_id} failed: {e}")

                if channel is None:
                    print("Channel still not found, skipping")
                    continue
                
                print(f"Got channel object: {channel.name}")
                try:
                    if channel:
                        print("Channel edit loop started")
                        for _ in range(MAX_RETRIES):
                            try:
                                print("Try edit in loop")
                                await asyncio.wait_for(channel.edit(name=new_name), timeout=2)
                                print("Edit success")
                                break
                            except asyncio.TimeoutError:
                                print(f"Edit timed out on retry {_}")
                                continue
                        print(f"Updated channel {channel.id} to {new_name}")

                    # Update last update time
                    self.last_update_times[channel_id] = int(time.time())
                    print("Modified last update time")

                except Exception as e:
                    logger.error(f"Failed to update channel {channel.id}: {e}")

                # Remove channel from queue
                self.pending_updates.pop(channel_id, None)
                await asyncio.sleep(0.5)
            print("updated channels section done")
    

    # Timer worker, handles scheduled name changes
    async def timer_worker(self):
        while True:
            await asyncio.sleep(60)  

            now = int(time.time())
            expired_timers = []

            for channel_id, end_time in self.timers.items():
                if now >= end_time:
                    expired_timers.append(channel_id)

            for channel_id in expired_timers:
                channel = self.bot.get_channel(channel_id)
                try:
                    if channel:
                        await self.set_emoji(channel, "close")
                        logger.debug(f"Timer expired for channel {channel.id}")

                    # Remove expired timer
                    del self.timers[channel_id]
                    
                except Exception as e:
                    logger.error(f"Failed to update channel {channel.id} after timer expired: {e}")


    # Queues a channel name update, replacing any previous updates for that channel
    def queue_update(self, channel: discord.TextChannel, new_name: str, manual: bool) -> bool:
        try:
            if new_name is None:
                self.pending_updates.pop(channel.id, None)
                return False

            print("channel name is", channel.name)
            print("new name is", new_name)
            
            if channel.name == new_name:
                self.pending_updates.pop(channel.id, None)
                return False
            
            current_name = self.pending_updates.get(channel.id, channel.name)

            print("current name is", current_name)
            print("new name is", new_name)

            # Drop update if it's the same as the current one
            if current_name == new_name:
                return False

            # Mapping of restricted transitions
            restricted_updates = {
                ("new", "alert"): "update denied, tried to set new to alert",
                ("inactive", "wait"): "update denied, tried to set inactive to wait",
                ("close", "wait"): "update denied, tried to set close to wait",
            }

            # Check for restricted automatic updates
            if not manual:
                for old_status, log_msg in restricted_updates.items():
                    if current_name.startswith(emojis.emoji_map.get(old_status[0], "")) and new_name.startswith(emojis.emoji_map.get(old_status[1], "")):
                        logger.debug(log_msg)
                        return False

                # Handle special case: deleting timer if switching from inactive/close to alert
                if current_name.startswith((emojis.emoji_map.get("inactive", ""), emojis.emoji_map.get("close", ""))) and new_name.startswith(emojis.emoji_map.get("alert", "")):
                    if self.timers.pop(channel.id, None):
                        logger.debug("timer deleted, set inactive or close to alert")

            # Queue the update
            self.pending_updates[channel.id] = new_name
            logger.debug(f"Queued update for {channel.name} {channel.id}: setting to {new_name}")
            return True

        except Exception as e:
            logger.exception(f"queue_update sent an error: {e}")
            return False  


    # Add emoji to the start of a channel's name
    async def set_emoji(self, channel: discord.TextChannel, emoji_str: str, manual: bool = False) -> bool:
        if emoji_str is None:
            self.queue_update(channel, None, manual)
            return True

        new_name = ""
        selected_emoji = emojis.emoji_map.get(emoji_str, "")

        # Remove prefixed emoji if there is one
        if (channel.name)[0] in emoji.EMOJI_DATA:
            new_name = f"{selected_emoji}{(channel.name)[1:]}" if selected_emoji else f"{emoji_str}{(channel.name)[1:]}"
        else:
            new_name = f"{selected_emoji}{channel.name}" if selected_emoji else f"{emoji_str}{channel.name}"

        return self.queue_update(channel, new_name, manual)


    # Check if the input is a valid Unicode emoji
    def check_unicode(self, input_emoji: str) -> bool:
        return input_emoji in emoji.EMOJI_DATA