from fastapi import APIRouter

from app.services.optimizer import optimize_routes
from app.api.routes.containers import container_readings

router = APIRouter()


@router.post("/optimize")
async def generate_optimized_routes(
    num_vehicles: int = 3,
    fill_threshold: float = 0.8,
):
    """Generate optimized collection routes based on current container data."""
    readings = list(container_readings.values())
    if not readings:
        return {"error": "No container data available"}

    result = optimize_routes(readings, num_vehicles, fill_threshold)
    return result
