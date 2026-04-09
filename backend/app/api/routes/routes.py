from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import require_collector_or_admin
from app.db.database import get_db
from app.db.models import ContainerReading, User
from app.models.schemas import ContainerReading as ContainerReadingSchema
from app.services.optimizer import optimize_routes

router = APIRouter()


@router.post("/optimize")
async def generate_optimized_routes(
    num_vehicles: int = 3,
    fill_threshold: float = 0.8,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_collector_or_admin),
):
    result = await db.execute(select(ContainerReading))
    rows = result.scalars().all()
    readings = [
        ContainerReadingSchema(**r.to_dict()) for r in rows
    ]
    if not readings:
        return {"error": "No container data available"}

    return optimize_routes(readings, num_vehicles, fill_threshold)
