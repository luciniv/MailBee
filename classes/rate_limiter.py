import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable, Dict
from utils.logger import *


class RateLimitBucket:
    def __init__(self, delay: float, max_concurrency: int = 10):
        self.delay = delay
        self.lock = asyncio.Lock()
        self.reset_time = 0.0
        self.semaphore = asyncio.Semaphore(max_concurrency)


class Queue:
    def __init__(self, max_actions_per_sec: int = 50):
        self.route_buckets: Dict[str, RateLimitBucket] = {}
        self.global_lock = asyncio.Lock()
        self.global_reset = 0.0
        self.call_timestamps = deque()
        self.max_actions_per_sec = max_actions_per_sec
        self.user_action_cooldowns = {
            "open_ticket_button": {},  # {user_id: timestamp}
            "dm_start": {},            # {user_id: timestamp}
        }
        self.per_user_cooldown_seconds = {
            "open_ticket_button": 5,  # seconds
            "dm_start": 5,
        }

        # Customize delays and concurrency per route type
        self.route_delays = {
            "dm_send": (1, 1),
            "message_send": (0.5, 10),
            "message_delete": (0.5, 5),
            "message_edit": (0.5, 5),
            "channel_edit": (0.5, 5),
            "add_reaction": (0.5, 5),
            "fetch_message": (1, 5),
            "fetch_member": (1, 5),
            "fetch_user": (1, 5),
            "fetch_generic": (1, 5),
            "generic": (1, 5),
        }

    def _classify_route(self, func: Callable, *args, **kwargs) -> str:
        name = func.__name__.lower()
        if "dm" in name or "create_dm" in name:
            return "dm_send"
        if "send" in name and "message" in name:
            return "message_send"
        if "delete" in name and "message" in name:
            return "message_delete"
        if "edit" in name and "message" in name:
            return "message_edit"
        if "edit" in name and "channel" in name:
            return "channel_edit"
        if "reaction" in name or "add_reaction" in name:
            return "add_reaction"
        if "fetch_member" in name:
            return "fetch_member"
        if "fetch_user" in name:
            return "fetch_user"
        if "fetch" in name:
            return "fetch_generic"
        return "generic"

    def _get_bucket(self, route: str) -> RateLimitBucket:
        if route not in self.route_buckets:
            delay, concurrency = self.route_delays.get(route, (0.5, 5))
            self.route_buckets[route] = RateLimitBucket(delay, concurrency)
        return self.route_buckets[route]

    async def _enforce_global_rate(self):
        now = time.time()
        while len(self.call_timestamps) >= self.max_actions_per_sec:
            if now - self.call_timestamps[0] > 1:
                self.call_timestamps.popleft()
            else:
                await asyncio.sleep(0.01)
                now = time.time()
        self.call_timestamps.append(now)

    async def call(self, func: Callable[..., Awaitable], *args, route_type: str = None, **kwargs) -> Any:
        route = route_type or self._classify_route(func, *args, **kwargs)
        bucket = self._get_bucket(route)

        async with bucket.semaphore:
            while True:
                now = time.time()

                async with self.global_lock:
                    if now < self.global_reset:
                        await asyncio.sleep(self.global_reset - now)

                async with bucket.lock:
                    if time.time() < bucket.reset_time:
                        print("sleeping for route:", route)
                        await asyncio.sleep(bucket.reset_time - time.time())
                    await self._enforce_global_rate()

                    try:
                        result = await func(*args, **kwargs)
                        bucket.reset_time = time.time() + bucket.delay
                        return result

                    except Exception as e:
                        if "429" in str(e):
                            self.global_reset = time.time() + 2
                            await asyncio.sleep(2)
                            continue
                        raise e
                    
    def check_user_action_cooldown(self, route: str, user_id: int):
        now = time.time()

        cooldowns = self.user_action_cooldowns.setdefault(route, {})
        attempts = cooldowns.setdefault("attempts", {})
        timestamps = cooldowns.setdefault("timestamps", {})
        notified = cooldowns.setdefault("notified", {})

        last_time = timestamps.get(user_id, 0)
        attempt_count = attempts.get(user_id, 0)
        was_notified = notified.get(user_id, False)

        base_delay = self.per_user_cooldown_seconds.get(route, 3)
        retry_after = (last_time + base_delay * (2 ** max(0, attempt_count - 1))) - now

        if retry_after > 0:
            return True, retry_after, was_notified

        # Reset attempt count if cooldown expired
        if now - last_time > base_delay * 4:
            attempt_count = 0

        # Update state
        attempts[user_id] = attempt_count + 1
        timestamps[user_id] = now
        notified[user_id] = False  # reset notification status

        return False, 0.0, False