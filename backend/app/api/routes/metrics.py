from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.schemas import MetricsResponse
from app.services.metrics import compute_metrics

router = APIRouter()


@router.get("/", response_model=MetricsResponse)
async def get_metrics(
    num_vehicles: int = 3,
    fill_threshold: float = 0.8,
    db: AsyncSession = Depends(get_db),
):
    data = await compute_metrics(db, num_vehicles=num_vehicles, fill_threshold=fill_threshold)
    return MetricsResponse(**data)
