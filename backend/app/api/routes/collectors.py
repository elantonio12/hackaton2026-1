from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Collector
from app.models.schemas import CollectorCreate, CollectorUpdate
from app.models.schemas import Collector as CollectorSchema

router = APIRouter()


@router.post("/", response_model=CollectorSchema)
async def create_collector(collector: CollectorCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    row = Collector(**collector.model_dump(), created_at=now, updated_at=now)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row.to_dict()


@router.get("/", response_model=list[CollectorSchema])
async def get_collectors(
    zona: str = None, activo: bool = None, db: AsyncSession = Depends(get_db)
):
    stmt = select(Collector)
    if zona:
        stmt = stmt.where(Collector.zona == zona)
    if activo is not None:
        stmt = stmt.where(Collector.activo == activo)
    result = await db.execute(stmt)
    return [r.to_dict() for r in result.scalars().all()]


@router.get("/{collector_id}", response_model=CollectorSchema)
async def get_collector(collector_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Collector).where(Collector.id == collector_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    return row.to_dict()


@router.put("/{collector_id}", response_model=CollectorSchema)
async def update_collector(
    collector_id: int, updates: CollectorUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Collector).where(Collector.id == collector_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row.to_dict()


@router.delete("/{collector_id}")
async def delete_collector(collector_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Collector).where(Collector.id == collector_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recolector no encontrado")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted", "id": collector_id}
