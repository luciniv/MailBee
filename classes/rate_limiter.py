# import discord
# import time
# import asyncio
# import json
# from typing import Optional
# import redis.asyncio as redis
# from collections import defaultdict

# REDIS_PREFIX = "ratelimit:"
# GLOBAL_KEY = REDIS_PREFIX + "global"

# import asyncio
# import logging
# from collections import defaultdict
# from typing import Callable, Any

# log = logging.getLogger(__name__)


# class RateLimitedQueue:
#     def __init__(self, name: str, handler: Callable, delay: float = 0.25, maxsize: int = 100):
#         self.name = name
#         self.handler = handler  # async function to call with args
#         self.delay = delay
#         self.queue = asyncio.Queue(maxsize=maxsize)
#         self.task = asyncio.create_task(self.worker())

#     async def worker(self):
#         while True:
#             args = await self.queue.get()
#             try:
#                 await self.handler(*args)
#                 await asyncio.sleep(self.delay)
#             except Exception as e:
#                 log.warning(f"[{self.name}] Error handling task: {e}")
#             finally:
#                 self.queue.task_done()

#     async def submit(self, *args):
#         try:
#             await self.queue.put(args)
#         except asyncio.QueueFull:
#             log.warning(f"[{self.name}] Queue full. Task dropped.")


# class QueueManager:
#     def __init__(self):
#         self.queues = {}

#     def add_queue(self, key: str, handler: Callable, delay: float, maxsize: int = 100):
#         self.queues[key] = RateLimitedQueue(key, handler, delay, maxsize)

#     async def submit(self, key: str, *args):
#         if key not in self.queues:
#             raise ValueError(f"No queue registered for key: {key}")
#         await self.queues[key].submit(*args)



# queue_manager = QueueManager()

# def setup_queues(bot):
#     async def handle_dm(user, content):
#         await user.send(content)

#     async def handle_ticket_message(channel, content):
#         await channel.send(content)

#     async def handle_log(channel, content):
#         await channel.send(content)  # Just another channel for logging

#     queue_manager.add_queue("dm", handle_dm, delay=0.35)
#     queue_manager.add_queue("ticket", handle_ticket_message, delay=0.25)
#     queue_manager.add_queue("log", handle_log, delay=0.5)

#     # add more as needed





# # Store cooldown for a specific key
# async def set_cooldown(r: redis.Redis, key: str, retry_after: float):
#     expire_at = time.time() + retry_after
#     await r.set(REDIS_PREFIX + key, str(expire_at), ex=int(retry_after + 1))

# # Get cooldown, returns 0 if expired
# async def get_cooldown(r: redis.Redis, key: str) -> float:
#     value = await r.get(REDIS_PREFIX + key)
#     if value:
#         expire_at = float(value)
#         now = time.time()
#         return max(0, expire_at - now)
#     return 0

# # Global lock
# async def is_globally_limited(r: redis.Redis) -> bool:
#     return await get_cooldown(r, "global") > 0

# async def set_global_lock(r: redis.Redis, retry_after: float):
#     await set_cooldown(r, "global", retry_after)


# dm_queues = defaultdict(asyncio.Queue)
# dm_workers_started = set()

# class QueuedDM:
#     def __init__(self, user_id: int, content: str, retries: int = 0):
#         self.user_id = user_id
#         self.content = content
#         self.retries = retries

# async def send_dm_worker(bot, user_id: int, max_retries=3):
#     if user_id in dm_workers_started:
#         return
#     dm_workers_started.add(user_id)

#     r = bot.redis
#     queue = dm_queues[user_id]
#     bucket = f"dm:{user_id}"

#     while True:
#         message: QueuedDM = await queue.get()
#         cooldown = await get_cooldown(r, bucket)
#         global_lock = await is_globally_limited(r)

#         if global_lock:
#             await asyncio.sleep(1)
#             await queue.put(message)
#             continue

#         if cooldown > 0:
#             await asyncio.sleep(cooldown)
#             await queue.put(message)
#             continue

#         try:
#             user = await bot.fetch_user(user_id)
#             await user.send(message.content)
#         except Exception as e:
#             if hasattr(e, "status") and e.status == 429:
#                 # Discord.py doesn't expose this directly, you may need to catch HTTPException and parse
#                 retry_after = float(getattr(e, "retry_after", 5.0))
#                 is_global = getattr(e, "global", False)

#                 if is_global:
#                     await set_global_lock(r, retry_after)
#                 else:
#                     await set_cooldown(r, bucket, retry_after)

#                 if message.retries < max_retries:
#                     message.retries += 1
#                     await queue.put(message)
#                 else:
#                     print(f"[DM] Max retries exceeded for user {user_id}. Dropping message.")
#                 await asyncio.sleep(retry_after)
#             else:
#                 print(f"[DM] Unexpected error for user {user_id}: {e}")




# async def safe_send_dm(user: discord.User, content: str):
#     try:
#         await user.send(content)
#         await asyncio.sleep(1.0)  # wait 1 second between DMs
#     except discord.Forbidden:
#         print(f"Cannot DM {user} - permissions or settings.")
#     except discord.HTTPException as e:
#         print(f"Failed to DM {user}: {e}")


# send_queue = asyncio.Queue()

# async def message_sender_loop(bot):
#     while True:
#         channel_id, kwargs = await send_queue.get()
#         try:
#             channel = bot.get_channel(channel_id)
#             if channel:
#                 await channel.send(**kwargs)
#             else:
#                 print(f"Channel {channel_id} not found.")
#         except discord.HTTPException as e:
#             print(f"Failed to send message: {e}")
#         await asyncio.sleep(1.5)  # global send rate: ~40 msgs/minute (safe)

# async def safe_send(channel: discord.TextChannel, **kwargs):
#     await send_queue.put((channel.id, kwargs))