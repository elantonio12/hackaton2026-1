"""Background snapshot loop for the metric_snapshots table.

Runs forever as a fire-and-forget asyncio task started in main.py
startup. Every SNAPSHOT_INTERVAL_SECONDS it computes the current
metrics and persists a single MetricSnapshot row.

The point: turn the live `/metrics/` view (instantaneous numbers) into
a history that the /admin/metricas page can plot. With a 5-minute
interval we get 288 rows/day — trivial for Postgres, dense enough
for smooth charts.
"""
from __future__ import annotations

import asyncio
import logging
import os

from app.db.database import async_session
from app.db.models import MetricSnapshot, Truck
from app.services.metrics import compute_metrics
from sqlalchemy import func, select

logger = logging.getLogger(__name__)

# Default 5 minutes. Override with METRICS_SNAPSHOT_SECONDS for tests.
SNAPSHOT_INTERVAL_SECONDS = int(os.environ.get("METRICS_SNAPSHOT_SECONDS", "300"))


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


async def snapshot_loop() -> None:
    """Forever-loop that writes a snapshot every SNAPSHOT_INTERVAL_SECONDS.

    Fires one immediate snapshot at boot so freshly deployed instances
    have at least one row to plot, then sleeps and repeats.
    """
    logger.info(
        "[metrics_snapshot] loop started, interval=%ds", SNAPSHOT_INTERVAL_SECONDS
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
