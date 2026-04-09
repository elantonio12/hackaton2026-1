"""In-memory buffer of recent container collections.

Why it exists: when a truck collects a container the backend resets
its `fill_level` to 0.05 in the DB, but the IoT sensor simulator on
vps2 has its own in-memory state for that container and keeps posting
fill levels around 0.85+ — overwriting the reset on the next bulk
ingest cycle (~10s later). The end result is that the dashboard
never sees collected containers turn green.

This module exposes a small ring buffer of recent collections that
the simulator polls each cycle so it can reset its local state and
stop posting stale values. Pure in-memory: no DB, no migration. The
buffer evicts entries older than `RETENTION_SECONDS` so it stays
bounded even with thousands of collections per day.
"""
from __future__ import annotations

import threading
import time
from typing import Iterable

# How long a collection event stays in the buffer. The simulator polls
# every ~10s, so 10 minutes is enough headroom for a missed poll, a
# transient backend restart, or a slow ingest cycle.
RETENTION_SECONDS: float = 600.0

# Cap the buffer size to defend against runaway producers (e.g. a bug
# that calls /collect in a loop). Old entries get evicted first.
MAX_ENTRIES: int = 50_000


class _CollectionsBuffer:
    """Thread-safe { container_id: collected_at_unix_ts } map."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, float] = {}

    def record(self, container_id: str) -> None:
        """Mark a container as collected at the current time."""
        now = time.time()
        with self._lock:
            self._data[container_id] = now
            self._evict_locked(now)

    def since(self, since_ts: float) -> list[dict]:
        """Return all collections recorded after `since_ts`.

        Result is a list of {container_id, collected_at} dicts. Sort
        order is undefined — the simulator only cares about the set
        of container_ids and the max timestamp it saw.
        """
        now = time.time()
        with self._lock:
            self._evict_locked(now)
            return [
                {"container_id": cid, "collected_at": ts}
                for cid, ts in self._data.items()
                if ts > since_ts
            ]

    def _evict_locked(self, now: float) -> None:
        """Drop entries older than RETENTION_SECONDS or beyond MAX_ENTRIES.

        Caller must hold self._lock.
        """
        cutoff = now - RETENTION_SECONDS
        # Drop expired
        expired = [cid for cid, ts in self._data.items() if ts < cutoff]
        for cid in expired:
            del self._data[cid]
        # If still over the cap, drop the oldest extras
        if len(self._data) > MAX_ENTRIES:
            sorted_items = sorted(self._data.items(), key=lambda kv: kv[1])
            keep = dict(sorted_items[-MAX_ENTRIES:])
            self._data = keep

    def size(self) -> int:
        with self._lock:
            return len(self._data)


# Module-level singleton — imported by trucks router (writer) and
# sensors router (reader) so they share the same buffer.
recent_collections = _CollectionsBuffer()
