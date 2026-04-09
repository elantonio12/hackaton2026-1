from fastapi import APIRouter, Depends
from sqlalchemy import select
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
    threshold: float = 0.8, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ContainerReading).where(ContainerReading.fill_level >= threshold)
    )
    critical = [r.to_dict() for r in result.scalars().all()]
    return {"count": len(critical), "containers": critical}
