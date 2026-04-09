from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ContainerReading
from app.models.schemas import ContainerReading as ContainerReadingSchema

router = APIRouter()


async def upsert_reading(db: AsyncSession, data: dict):
    stmt = pg_insert(ContainerReading).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["container_id"],
        set_={k: stmt.excluded[k] for k in data if k != "container_id"},
    )
    await db.execute(stmt)
    await db.commit()


@router.post("/readings")
async def receive_reading(reading: ContainerReadingSchema, db: AsyncSession = Depends(get_db)):
    await upsert_reading(db, reading.model_dump())
    from app.services.prediction import append_reading
    append_reading(reading)
    return {"status": "received", "container_id": reading.container_id}


@router.post("/readings/bulk")
async def receive_bulk_readings(
    readings: list[ContainerReadingSchema],
    db: AsyncSession = Depends(get_db),
):
    """Bulk ingest for high-throughput simulators (10K+ sensors).

    Performs a single batch upsert and commit, then updates the in-memory
    prediction history for each reading.
    """
    if not readings:
        return {"status": "received", "count": 0}

    # Batch upsert: one pg_insert with ON CONFLICT per row, single commit
    payloads = [r.model_dump() for r in readings]
    for data in payloads:
        stmt = pg_insert(ContainerReading).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["container_id"],
            set_={k: stmt.excluded[k] for k in data if k != "container_id"},
        )
        await db.execute(stmt)
    await db.commit()

    # Feed in-memory prediction history
    from app.services.prediction import append_reading
    for reading in readings:
        append_reading(reading)

    return {"status": "received", "count": len(readings)}


@router.get("/readings", response_model=list[ContainerReadingSchema])
async def get_all_readings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContainerReading))
    return [r.to_dict() for r in result.scalars().all()]


@router.get("/readings/{container_id}", response_model=ContainerReadingSchema)
async def get_reading(container_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContainerReading).where(ContainerReading.container_id == container_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"error": "Container not found"}
    return row.to_dict()


@router.get("/critical")
async def get_critical_containers(
    threshold: float = 0.8,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return critical containers ordered by fill level (most full first).

    Paginated to prevent DOM overflow when thousands of containers are
    above the threshold. Use `total` for the full count and `limit`/`offset`
    to page through results.
    """
    # Total count (cheap single query)
    total_result = await db.execute(
        select(func.count())
        .select_from(ContainerReading)
        .where(ContainerReading.fill_level >= threshold)
    )
    total = total_result.scalar() or 0

    # Page of most-critical containers
    page_result = await db.execute(
        select(ContainerReading)
        .where(ContainerReading.fill_level >= threshold)
        .order_by(ContainerReading.fill_level.desc())
        .limit(limit)
        .offset(offset)
    )
    critical = [r.to_dict() for r in page_result.scalars().all()]

    return {
        "total": total,
        "count": len(critical),
        "limit": limit,
        "offset": offset,
        "containers": critical,
    }
