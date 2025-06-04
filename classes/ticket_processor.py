# import asyncio
# import discord
# from discord import NotFound
# from collections import namedtuple
# from utils import logger

# TicketRequest = namedtuple("TicketRequest", ["userID", "guildID", "categoryID", "type_name", "modal_input"])
# ticket_queue: list[TicketRequest] = []


# class TicketProcessor:
#     def __init__(self, bot):
#         self.bot = bot
#         self.cooldown = 300 
#         self.worker_task = None
#         self.timer_worker_task = None
#         self.timers = {}  # Stores ticket close timers


#     # Start worker 
#     async def start_worker(self):
#         try:
#             self.worker_task = asyncio.create_task(self.worker())
#             logger.success("Workers started")
#         except Exception as e:
#             logger.error(f"Error starting workers: {e}")


#     # Shutdown worker gracefully
#     async def shutdown(self):
#         try:
#             self.worker_task.cancel()
#             logger.success("Workers shut down")

#         except Exception as e:
#             logger.exception(f"Error shutting down workers: {e}")


#     # Worker, attempts to edit a channel's name in the queue after 5 minutes
#     # Cooldown is local to each channel, set by Discord's ratelimiting (oh well, what can one do)
#     async def worker(self): 
#         while True:
#             try:
#                 await asyncio.sleep(20)  # Prevents high CPU usage
#                 now = int(time.time())
#                 channels_to_update = []

#                 # Collect channels that are ready to be updated
#                 for channel_id, new_name in list(self.pending_updates.items()):

#                     last_update_time = self.last_update_times.get(channel_id, None)
#                     if (last_update_time is None):
#                         if (new_name.startswith(emojis.emoji_map.get("new", ""))):
#                             last_update_time = now - self.cooldown
#                         else:
#                             last_update_time = now
#                             self.last_update_times[channel_id] = now

#                     if (now - last_update_time) >= self.cooldown:
#                         channels_to_update.append((channel_id, new_name))

#                 # Apply updates for ready channels
#                 for channel_id, new_name in channels_to_update:
#                     try:
#                         channel = self.bot.get_channel(channel_id)
#                         if channel is None:
#                             print("Channel not cached, attempting fetch")
#                             channel = await asyncio.wait_for(self.bot.fetch_channel(channel_id), timeout=2)
#                     except asyncio.TimeoutError:
#                         print("channel fetch timeout error")

#                     except discord.NotFound:
#                         print(f"Channel {channel_id} was deleted")
                        
#                     except Exception as e:
#                         print(f"Fetching channel {channel_id} failed: {e}")
                    
#                     try:
#                         if channel:
#                             for _ in range(MAX_RETRIES):
#                                 try:
#                                     await asyncio.wait_for(channel.edit(name=new_name), timeout=2)
#                                     break
#                                 except asyncio.TimeoutError:
#                                     continue

#                         # Update last update time
#                         self.last_update_times[channel_id] = int(time.time())

#                     except Exception as e:
#                         logger.error(f"Failed to update channel {channel.id}: {e}")

#                     # Remove channel from queue
#                     self.pending_updates.pop(channel_id, None)
#                     await asyncio.sleep(0.5)
#             except Exception as e:
#                 logger.exception(f"Channel worker sent an error: {e}")
    


#     async def worker(self):
#         while True:
#             await asyncio.sleep(10)

#             # Group tickets by guild and category to minimize category fetches
#             grouped = {}
#             for ticket in ticket_queue:
#                 key = (ticket.guild_id, ticket.category_id)
#                 grouped.setdefault(key, []).append(ticket)

#             to_remove = []
#             for (guild_id, category_id), tickets in grouped.items():
#                 guild = bot.get_guild(guild_id)
#                 if not guild:
#                     continue

#                 # FIXME cache system
#                 category = guild.get_channel(category_id)
#                 if not category:
#                     continue

#                 ticket_count = len([c for c in category.channels if isinstance(c, discord.TextChannel)])
#                 available_slots = 50 - ticket_count
#                 process_now = tickets[:available_slots]
#                 queued = tickets[available_slots:]

#                 for ticket in process_now:
#                     member = await self.bot.cache.get_user(ticket.user_id)
#                     if member:

#                         await open_ticket(ticket, member, category)
#                         to_remove.append(ticket)

#                 for idx, ticket in enumerate(queued, start=1):
#                     await update_queue_dm(bot, ticket.user_id, guild_id, idx)

#             ticket_queue[:] = [t for t in ticket_queue if t not in to_remove]


#     async def process_ready_tickets(bot, ready_tickets):
#         tasks = []

#         for ticket in ready_tickets:
#             guild = bot.get_guild(ticket.guild_id)
#             category = guild.get_channel(ticket.category_id)
#             if not category:
#                 continue

#             tasks.append(process_single_ticket(bot, ticket, guild, category))

#         # Run them all at once
#         await asyncio.gather(*tasks, return_exceptions=True)


#     async def process_ready_tickets_staggered(bot, ready_tickets):
#         for i, ticket in enumerate(ready_tickets):
#             guild = bot.get_guild(ticket.guild_id)
#             category = guild.get_channel(ticket.category_id)
#             if not category:
#                 continue

#             asyncio.create_task(process_single_ticket(bot, ticket, guild, category))
#             await asyncio.sleep(0.2) 