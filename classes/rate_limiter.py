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

        # Customize delays and concurrency per route type
        self.route_delays = {
            "dm_send": (0.5, 2),
            "message_send": (0.2, 10),
            "message_delete": (0.2, 10),
            "message_edit": (0.2, 10),
            "channel_edit": (0.5, 5),
            "add_reaction": (0.5, 5),
            "fetch_member": (0.1, 10),
            "fetch_user": (0.1, 10),
            "fetch_generic": (0.1, 10),
            "generic": (0.1, 10),
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
            delay, concurrency = self.route_delays.get(route, (0.1, 10))
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
        logger.debug(f"api function called: route: {route}")

        async with bucket.semaphore:
            logger.debug("got semaphore")
            while True:
                now = time.time()

                async with self.global_lock:
                    if now < self.global_reset:
                        await asyncio.sleep(self.global_reset - now)

                async with bucket.lock:
                    if time.time() < bucket.reset_time:
                        logger.warning("enforcing local ratelimit")
                        await asyncio.sleep(bucket.reset_time - time.time())
                        logger.warning("enforced local ratelimit")
                    await self._enforce_global_rate()

                    try:
                        logger.debug("executing function")
                        result = await func(*args, **kwargs)
                        logger.debug("executed")
                        bucket.reset_time = time.time() + bucket.delay
                        return result

                    except Exception as e:
                        if "429" in str(e):
                            self.global_reset = time.time() + 2
                            await asyncio.sleep(2)
                            continue
                        raise e