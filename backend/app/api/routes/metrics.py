from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import ttl_cache
from app.db.database import async_session, get_db
from app.db.models import MetricSnapshot
from app.models.schemas import MetricsResponse
from app.services.metrics import compute_metrics

router = APIRouter()

# /metrics/ runs compute_metrics() which iterates ~10K rows AND triggers
# a Granite TTM forward pass. Both are cheap individually but the endpoint
# is polled every 15-20s by every open admin tab. With this TTL the
# expensive computation runs at most once per window across all callers.
METRICS_CACHE_TTL = 15.0


@router.get("/", response_model=MetricsResponse)
async def get_metrics(
    num_vehicles: int = 3,
    fill_threshold: float = 0.8,
):
    cache_key = f"metrics:summary:{num_vehicles}:{fill_threshold}"

    async def _load() -> dict:
        async with async_session() as db:
            return await compute_metrics(
                db, num_vehicles=num_vehicles, fill_threshold=fill_threshold
            )

    data = await ttl_cache.get_or_set(
        key=cache_key, ttl=METRICS_CACHE_TTL, loader=_load
    )
    return MetricsResponse(**data)


@router.get("/history")
async def get_metrics_history(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """Return persisted metric snapshots for the last `hours` hours.

    Snapshots are written by the background loop in main.py every 5
    minutes (288 rows/day). The /admin/metricas page consumes this to
    render time-series charts of CO2 saved, critical containers, and
    fleet activity.

    Output is ordered oldest -> newest so the frontend can plot
    directly without sorting.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.timestamp >= cutoff)
        .order_by(MetricSnapshot.timestamp.asc())
    )
    rows = result.scalars().all()
    return {
        "hours": hours,
        "count": len(rows),
        "snapshots": [r.to_dict() for r in rows],
    }
