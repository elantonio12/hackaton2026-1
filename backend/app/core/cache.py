"""In-process TTL cache for hot read-only endpoints.

Goal: stop hammering Postgres for endpoints that get polled every few
seconds by every open admin tab. The dashboard refreshes /containers/
readings (≈1.5 MB JSON over 10K rows) every 30s — N admins → N×ratio
of identical heavy queries. With a 30s TTL cache they collapse to one.

Design:
- Pure in-memory dict per worker process. NOT shared across uvicorn
  workers — each gets its own copy. That's fine: cache misses just
  fall through to the DB and the cost of a 2x miss rate is much smaller
  than the cost of running Redis at this stage.
- Coalesces concurrent misses with an asyncio.Lock per key — when 50
  requests arrive simultaneously and the cache is cold, only ONE
  fetcher runs the loader and the others wait on the result. This is
  the actual win at scale.
- Keys are strings (compose your own from the endpoint + query params).

Usage:
    @router.get("/readings")
    async def get_all_readings(db: AsyncSession = Depends(get_db)):
        return await ttl_cache.get_or_set(
            key="containers/readings",
            ttl=30,
            loader=lambda: _fetch_all_readings(db),
        )
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)
        self._locks: dict[str, asyncio.Lock] = {}        # key -> singleflight lock
        self._global_lock = asyncio.Lock()               # protects _locks dict

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def get_or_set(
        self,
        key: str,
        ttl: float,
        loader: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return cached value, or call `loader()` once and cache the result.

        Concurrent misses for the same key collapse to a single loader
        invocation. Subsequent waiters get the same result.
        """
        # Fast path: hit
        entry = self._store.get(key)
        now = time.monotonic()
        if entry is not None and entry[0] > now:
            return entry[1]

        # Slow path: serialize the loader behind the per-key lock
        lock = await self._lock_for(key)
        async with lock:
            # Re-check inside the lock — another waiter may have already loaded
            entry = self._store.get(key)
            now = time.monotonic()
            if entry is not None and entry[0] > now:
                return entry[1]

            value = await loader()
            self._store[key] = (now + ttl, value)
            return value

    def invalidate(self, key: str) -> None:
        """Drop a single key from the cache (e.g. after a write)."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Drop everything. Used in tests."""
        self._store.clear()


# Process-global cache instance. Importing modules use this directly.
ttl_cache = TTLCache()
