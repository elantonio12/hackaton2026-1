"""Process and thread pools for offloading CPU-bound work.

The asyncio event loop must never run blocking computation directly —
when it does, every other in-flight HTTP request stalls until the
blocking call returns. We have two such hot spots:

1. **OR-Tools CVRP solver** (services/vrp_solver.solve)
   Pure Python + C++ search. ~5s for a 30-truck / 1500-container
   problem. Has no shared in-memory state with the API process — only
   needs OSRM (HTTP) and the input dataclasses. *Process pool friendly.*

2. **IBM Granite TTM batched inference** (services/prediction.predict_all)
   Reads `container_history` and `predictor` from the worker process's
   own memory. *Cannot* be moved to a child process without re-loading
   the model. But the heavy work is numpy/torch C code which releases
   the GIL while computing — so a thread executor still gives true
   parallelism with the rest of the asyncio loop.

Helpers:
- `run_in_process(fn, *args)`: ProcessPoolExecutor for the VRP solver.
- `run_in_thread(fn, *args)`: ThreadPoolExecutor for predict_all and
  any other "calls into a C extension that releases the GIL" workload.

Both return awaitables, so call sites just `await` them.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Pool sizing
# ---------------------------------------------------------------------------
# Process pool: only the VRP solver uses it. 1 worker is enough — at our
# scale (30 trucks) one solve runs in 5s and the admin clicks Optimizar
# at most a few times per session.
PROCESS_POOL_WORKERS = int(os.environ.get("PROCESS_POOL_WORKERS", "1"))

# Thread pool: shared by predict_all and any other non-async helper.
# Bigger because predictions might fan out per request and we want them
# to overlap with other I/O-bound async work.
THREAD_POOL_WORKERS = int(os.environ.get("THREAD_POOL_WORKERS", "4"))

_process_pool: ProcessPoolExecutor | None = None
_thread_pool: ThreadPoolExecutor | None = None


def _get_process_pool() -> ProcessPoolExecutor:
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor(max_workers=PROCESS_POOL_WORKERS)
        logger.info(
            "[executors] ProcessPoolExecutor started with %d workers",
            PROCESS_POOL_WORKERS,
        )
    return _process_pool


def _get_thread_pool() -> ThreadPoolExecutor:
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(
            max_workers=THREAD_POOL_WORKERS,
            thread_name_prefix="ecoruta-cpu",
        )
        logger.info(
            "[executors] ThreadPoolExecutor started with %d workers",
            THREAD_POOL_WORKERS,
        )
    return _thread_pool


async def run_in_process(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run `fn` in the dedicated ProcessPoolExecutor and await the result.

    Use this for true CPU-bound Python work that needs to bypass the GIL
    (OR-Tools VRP solving). The function and its arguments must be
    pickleable.
    """
    loop = asyncio.get_running_loop()
    pool = _get_process_pool()
    if kwargs:
        # ProcessPoolExecutor.submit takes only positional args. Wrap with
        # functools.partial so kwargs survive the trip.
        from functools import partial
        return await loop.run_in_executor(pool, partial(fn, *args, **kwargs))
    return await loop.run_in_executor(pool, fn, *args)


async def run_in_thread(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run `fn` in the dedicated ThreadPoolExecutor and await the result.

    Use this for CPU-bound work that touches in-process state (e.g.
    Granite TTM predictor — it lives in this worker's memory and can't
    be pickled across processes). The GIL is still in play, but C
    extensions like numpy/torch release it during heavy computation,
    so other async work continues to make progress.
    """
    loop = asyncio.get_running_loop()
    pool = _get_thread_pool()
    if kwargs:
        from functools import partial
        return await loop.run_in_executor(pool, partial(fn, *args, **kwargs))
    return await loop.run_in_executor(pool, fn, *args)


def shutdown_executors() -> None:
    """Tear down both pools cleanly. Called from FastAPI shutdown."""
    global _process_pool, _thread_pool
    if _process_pool is not None:
        _process_pool.shutdown(wait=False, cancel_futures=True)
        _process_pool = None
    if _thread_pool is not None:
        _thread_pool.shutdown(wait=False, cancel_futures=True)
        _thread_pool = None
