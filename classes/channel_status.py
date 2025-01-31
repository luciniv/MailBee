import discord
import asyncio
import emoji
from utils import emojis
from datetime import datetime, timezone, timedelta
from utils.logger import *


class ChannelStatus:
    def __init__(self):
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
            await self.worker_task.cancel()
            await self.worker_task

        except asyncio.CancelledError:
            logger.success("Worker shut down")
            pass

        except Exception as e:
            logger.error(f"Error shutting down worker: {e}")


    async def worker(self):
        while True:
            await asyncio.sleep(1)  # Prevents high CPU usage

            now = datetime.now(timezone.utc)
            channels_to_update = []

            # Collect channels that are ready to be updated
            for channel_id, (channel, new_name) in list(self.pending_updates.items()):
                last_update_time = self.last_update_times.get(channel_id, now - self.cooldown)
                if (now - last_update_time) >= self.cooldown:
                    channels_to_update.append((channel_id, channel, new_name))

            # Apply updates for ready channels
            for channel_id, channel, new_name in channels_to_update:
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
    def queue_update(self, channel: discord.TextChannel, new_name: str) -> bool:
        self.pending_updates[channel.id] = (channel, new_name)
        logger.debug(f"Queued update for channel {channel.id}: {new_name}")


    # Add emoji to the start of a channel's name
    async def set_emoji(self, channel: discord.TextChannel, emoji_str: str):
        new_name = ""
        selected_emoji = emojis.emoji_map.get(emoji_str, "")

        if ((channel.name).startswith(emojis.emoji_map.get("new", ""))) and (emoji_str == "alert"):
            return False

        # Remove prefixed emoji if there is one
        if (channel.name)[0] in emoji.EMOJI_DATA:
            new_name = f"{selected_emoji}{(channel.name)[1:]}" if selected_emoji else f"{emoji_str}{(channel.name)[1:]}"
        else:
            new_name = f"{selected_emoji}{channel.name}" if selected_emoji else f"{emoji_str}{channel.name}"

        await self.queue_update(channel, new_name)
        return True


    # Check if the input is a valid Unicode emoji
    def check_unicode(self, input_emoji: str) -> bool:
        return input_emoji in emoji.EMOJI_DATA