import discord
import asyncio
import emoji
from utils import emojis
from datetime import datetime, timezone, timedelta
from utils.logger import *


class ChannelStatus:
    def __init__(self, bot):
        self.bot = bot
        self.last_update_times = {}
        self.pending_updates = {}  # Stores only the latest update per channel
        self.cooldown = timedelta(minutes=5.05)  # 1 update per ~5 minutes
        self.worker_task = None


    # Start worker 
    async def start_worker(self):
        try:
            self.worker_task = asyncio.create_task(self.worker())
            logger.success("Worker started")
        except Exception as e:
            logger.error(f"Error starting worker: {e}")


    # Shutdown worker gracefully
    async def shutdown(self):
        try:
            self.worker_task.cancel()
            logger.success("Worker shut down")

        except Exception as e:
            logger.exception(f"Error shutting down worker: {e}")


    # Worker, attempts to edit a channel's name in the queue after 5 minutes
    # Cooldown is local to each channel, set by Discord's ratelimiting (oh well, what can one do)
    async def worker(self): 
        while True:
            await asyncio.sleep(2)  # Prevents high CPU usage

            now = datetime.now(timezone.utc)
            channels_to_update = []

            # Collect channels that are ready to be updated
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

            # Apply updates for ready channels
            for channel_id, new_name in channels_to_update:
                channel = self.bot.get_channel(channel_id)
                try:
                    if channel.name != new_name:
                        await channel.edit(name=new_name)
                        logger.debug(f"Updated channel {channel.id} to {new_name}")

                    # Update last update time
                    self.last_update_times[channel_id] = datetime.now(timezone.utc)

                except Exception as e:
                    logger.error(f"Failed to update channel {channel.id}: {e}")

                # Remove channel from queue
                self.pending_updates.pop(channel_id, None)


    # Queues a channel name update, replacing any previous updates for that channel
    def queue_update(self, channel: discord.TextChannel, new_name: str, manual: bool) -> bool:
        try:
            if new_name is None:
                self.pending_updates.pop(channel.id, None)
                return
            
            # Automatic updates, do not allow "new" overwrites by "alert"
            if not manual:
                if self.pending_updates.get(channel.id):
                    if ((self.pending_updates[channel.id]).startswith(emojis.emoji_map.get("new", "")) and (new_name.startswith(emojis.emoji_map.get("alert", "")))):
                        return False
                else:
                    if ((channel.name).startswith(emojis.emoji_map.get("new", "")) and new_name.startswith(emojis.emoji_map.get("alert", ""))): 
                        return False
                    
            # Manual updates, allow "new" overwrites
            if self.pending_updates.get(channel.id):
                if ((self.pending_updates[channel.id]) == new_name):
                    return False
            else:
                if (channel.name == new_name):
                    return False
                
            self.pending_updates[channel.id] = new_name
            logger.debug(f"Queued update for channel {channel.id}: {new_name}")
            return True

        except Exception as e:
            logger.error(f"queue_update sent an error: {e}")


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