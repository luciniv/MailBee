import discord
import asyncio
import emoji
import time
from utils import emojis
from utils.logger import *
from cogs.tools import close_ticket


class ChannelStatus:
    def __init__(self, bot):
        self.bot = bot
        self.last_update_times = {}  # Stores only the latest update per channel
        self.pending_updates = {}  # Stores text newname 
        self.cooldown = 305  # 1 update per ~5 minutes
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
            try:
                await asyncio.sleep(20)  # Prevents high CPU usage
                now = int(time.time())
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

                # NOTE look into this system sometime
                # Apply updates for ready channels
                for channel_id, new_name in channels_to_update:
                    channel = await self.bot.cache.get_channel(channel_id)
                    pop_flag = True
                    try:
                        if channel: 
                            try:
                                await asyncio.wait_for(channel.edit(name=new_name), timeout=1)
                            except asyncio.TimeoutError:
                                logger.error(f"Status update timed out for channel {channel.name} ({channel_id})")
                                pop_flag = False
                            except discord.NotFound:
                                logger.error(f"Channel not found for update {channel.name} ({channel_id})")
                            except Exception as e:
                                logger.error(f"Status update errored for channel {channel.name} ({channel_id}): {e}")
                                pop_flag = False

                        # Update last update time
                        self.last_update_times[channel_id] = int(time.time())

                    except Exception as e:
                        logger.error(f"Failed to update channel {channel.id}: {e}")

                    # Remove channel from queue
                    if pop_flag:
                        self.pending_updates.pop(channel_id, None)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.exception(f"Channel worker sent an error: {e}")
    

    # Timer worker, handles scheduled name changes
    async def timer_worker(self):
        while True:
            try:
                await asyncio.sleep(60)  
                now = int(time.time())
                expired_timers = []

                for channelID, fields in self.timers.items():
                    end_time, modID, openerID, reason = fields
                    if now >= int(end_time):
                        expired_timers.append((channelID, modID, openerID, reason))

                for channelID, modID, openerID, reason in expired_timers:
                    premature_delete = False
                    channel = self.bot.get_channel(channelID)
                    if channel is None:
                        try:
                            channel = await asyncio.wait_for(self.bot.fetch_channel(channelID), timeout=1)
                        except discord.NotFound:
                            premature_delete = True
                        except Exception:
                            pass

                    if channel is not None:
                        try:
                            guild = channel.guild
                            member = await self.bot.cache.get_guild_member(guild, modID)
                            
                            await close_ticket(self.bot, channel, member, openerID, guild.id, reason, None, True)
                            logger.debug(f"Timer expired for channel {channel.id}")

                        except Exception as e:
                            logger.error(f"Failed to update channel {channel.id} after timer expired: {e}")

                    elif premature_delete:
                        pass
                        # FIXME edge case, channel with timer is deleted
                        # user = await self.bot.cache.get_user(userID)
                        # await close_ticket(self.bot, channelID, user, reason, None, True)

                    # Remove expired timer
                    self.timers.pop(channelID, None)
                    await self.bot.data_manager.save_timers_to_redis()
                    await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)
                    

    # Queues a channel name update, replacing any previous updates for that channel
    def queue_update(self, channel: discord.TextChannel, new_name: str, manual: bool) -> bool:
        try:
            if new_name is None:
                self.pending_updates.pop(channel.id, None)
                return False
            
            if channel.name == new_name:
                self.pending_updates.pop(channel.id, None)
                return False
            
            current_name = self.pending_updates.get(channel.id, channel.name)

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
                        return False

                # Handle special case: deleting timer if switching from inactive/close to alert
                if current_name.startswith((emojis.emoji_map.get("inactive", ""), emojis.emoji_map.get("close", ""))) and new_name.startswith(emojis.emoji_map.get("alert", "")):
                    if self.timers.pop(channel.id, None):
                        pass

            # Queue the update
            self.pending_updates[channel.id] = new_name
            return True

        except Exception as e:
            logger.exception(f"queue_update sent an error: {e}")
            return False  


    # Add emoji to the start of a channel's name
    async def set_emoji(self, channel: discord.TextChannel, emoji_str: str, manual: bool = False, nsfw: bool = None) -> bool:
        new_name = ""
        if nsfw is not None:
            current_name = self.pending_updates.get(channel.id, channel.name)

            # nsfw is True, make name nsfw
            if nsfw:
                if any((current_name).startswith(value) for value in emojis.emoji_map.values()):
                    new_name = f"{(current_name)[0]}{emojis.emoji_map.get('nsfw', '🔞')}{(current_name)[1:]}"

            # nsfw is false, make name non-nsfw
            elif not nsfw:
                if any((current_name).startswith(value) for value in emojis.emoji_map.values()):
                    new_name = f"{(current_name)[0]}{(current_name)[2:]}"

        else:
            if emoji_str is None:
                self.queue_update(channel, None, manual)
                return True

            selected_emoji = emojis.emoji_map.get(emoji_str, "")

            # Remove prefixed emoji if there is one
            if (channel.name)[0] in emoji.EMOJI_DATA and (not channel.name.startswith(emojis.emoji_map.get("nsfw", "🔞"))):
                new_name = f"{selected_emoji}{(channel.name)[1:]}" if selected_emoji else f"{emoji_str}{(channel.name)[1:]}"
            else:
                new_name = f"{selected_emoji}{channel.name}" if selected_emoji else f"{emoji_str}{channel.name}"

        return self.queue_update(channel, new_name, manual)


    # Check if the input is a valid Unicode emoji
    def check_unicode(self, input_emoji: str) -> bool:
        return input_emoji in emoji.EMOJI_DATA
    

    async def add_timer(self, channelID, time, modID, openerID, reason):
        self.timers[channelID] = [time, modID, openerID, reason]
        await self.bot.data_manager.save_timers_to_redis()


    async def remove_timer(self, channelID):
        if self.timers.pop(channelID, None) is not None:
            await self.bot.data_manager.save_timers_to_redis()
            return True
        return False
    

    def get_timer(self, channelID):
        timer = self.timers.get(channelID, None)
        return timer
