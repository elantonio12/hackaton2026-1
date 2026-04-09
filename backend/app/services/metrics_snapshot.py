"""Background snapshot loop for the metric_snapshots table.

Runs forever as a fire-and-forget asyncio task started in main.py
startup. Every SNAPSHOT_INTERVAL_SECONDS it computes the current
metrics and persists a single MetricSnapshot row.

The point: turn the live `/metrics/` view (instantaneous numbers) into
a history that the /admin/metricas page can plot. With a 5-minute
interval we get 288 rows/day — trivial for Postgres, dense enough
for smooth charts.

Multi-worker note: when uvicorn runs with --workers > 1 we have N
processes booting at once. Without coordination every worker would
start its own snapshot loop and we'd get N rows per interval. We
use a POSIX advisory file lock (fcntl.flock) to elect a single
"leader" worker — the first process to grab the lock runs the loop,
the rest skip it. When the leader dies, the kernel releases the lock
and the next worker to retry takes over.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os

from sqlalchemy import func, select

from app.db.database import async_session
from app.db.models import MetricSnapshot, Truck
from app.services.metrics import compute_metrics

logger = logging.getLogger(__name__)

# Default 5 minutes. Override with METRICS_SNAPSHOT_SECONDS for tests.
SNAPSHOT_INTERVAL_SECONDS = int(os.environ.get("METRICS_SNAPSHOT_SECONDS", "300"))

# Path to the leader-election lock file. Lives inside /tmp because all
# uvicorn workers share the same filesystem within the container.
LEADER_LOCK_PATH = os.environ.get(
    "METRICS_SNAPSHOT_LOCK_PATH", "/tmp/ecoruta-snapshot-leader.lock"
)

# Module-global file descriptor for the held lock. We MUST keep this
# fd alive for the entire lifetime of the leader process — closing it
# releases the lock. Storing it in a module global is the simplest way
# to anchor it.
_leader_fd: int | None = None


async def write_snapshot() -> MetricSnapshot | None:
    """Compute current metrics and persist one MetricSnapshot row."""
    try:
        async with async_session() as db:
            data = await compute_metrics(db)

            # Fleet counts come from a separate query (compute_metrics
            # focuses on containers + efficiency, not fleet sizing).
            total_trucks = (
                await db.execute(select(func.count()).select_from(Truck))
            ).scalar() or 0
            active_trucks = (
                await db.execute(
                    select(func.count())
                    .select_from(Truck)
                    .where(Truck.status.in_(["en_route", "collecting", "returning"]))
                )
            ).scalar() or 0

            # Average fill across the live readings, from the zones rollup
            zones = data.get("zones") or []
            total_containers = data["system"]["total_containers_monitored"]
            avg_fill = (
                sum(z["avg_fill_level"] * z["total_containers"] for z in zones)
                / total_containers
                if total_containers > 0
                else 0.0
            )

            snap = MetricSnapshot(
                total_containers=data["system"]["total_containers_monitored"],
                critical_containers=data["system"]["containers_critical"],
                avg_fill_level=round(avg_fill, 4),
                predicted_full_24h=data["system"]["containers_predicted_full_24h"],
                fleet_total=total_trucks,
                fleet_active=active_trucks,
                active_routes=data["efficiency"]["vehicles_used"],
                optimized_km=data["efficiency"]["optimized_distance_km"],
                saved_km=data["efficiency"]["distance_saved_km"],
                distance_reduction_pct=data["efficiency"]["distance_reduction_pct"],
                fuel_saved_liters=data["environmental"]["fuel_saved_liters"],
                co2_avoided_kg=data["environmental"]["co2_avoided_kg"],
                fuel_cost_saved_mxn=data["environmental"]["fuel_cost_saved_mxn"],
            )
            db.add(snap)
            await db.commit()
            return snap
    except Exception:
        logger.exception("[metrics_snapshot] failed to write snapshot")
        return None


def _try_become_leader() -> bool:
    """Attempt to acquire the leader lock with non-blocking flock.

    Returns True if this process is now the leader. Stores the lock
    fd in `_leader_fd` so the file stays open for the lifetime of the
    process — releasing the fd releases the lock.
    """
    global _leader_fd
    try:
        fd = os.open(LEADER_LOCK_PATH, os.O_WRONLY | os.O_CREAT, 0o644)
    except OSError:
        logger.exception("[metrics_snapshot] could not open lock file")
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    except OSError:
        os.close(fd)
        logger.exception("[metrics_snapshot] flock failed")
        return False
    _leader_fd = fd
    return True


async def snapshot_loop() -> None:
    """Forever-loop that writes a snapshot every SNAPSHOT_INTERVAL_SECONDS.

    Multi-worker safe: only the worker that wins the flock-based
    leader election does the actual work. Followers return
    immediately so the API throughput is identical to a single-worker
    deploy.

    Fires one immediate snapshot at boot so freshly deployed instances
    have at least one row to plot, then sleeps and repeats.
    """
    # Wait a moment for the connection pool to be ready
    await asyncio.sleep(2)

    if not _try_become_leader():
        logger.info("[metrics_snapshot] follower worker — skipping loop")
        return

    logger.info(
        "[metrics_snapshot] leader worker — loop started, interval=%ds",
        SNAPSHOT_INTERVAL_SECONDS,
    )
    # Initial snapshot — wait a bit so the prediction model has time to train
    # and the simulator has at least one tick of data.
    await asyncio.sleep(30)
    await write_snapshot()

    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        snap = await write_snapshot()
        if snap is not None:
            logger.info(
                "[metrics_snapshot] saved snapshot id=%s critical=%d co2=%.1fkg",
                snap.id, snap.critical_containers, snap.co2_avoided_kg,
            )
