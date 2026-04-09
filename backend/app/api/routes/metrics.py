from fastapi import APIRouter

from app.models.schemas import MetricsResponse
from app.services.metrics import compute_metrics

router = APIRouter()


@router.get("/", response_model=MetricsResponse)
async def get_metrics(num_vehicles: int = 3, fill_threshold: float = 0.8):
    """Get operational, environmental, and financial metrics."""
    data = compute_metrics(num_vehicles=num_vehicles, fill_threshold=fill_threshold)
    return MetricsResponse(**data)
