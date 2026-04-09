from fastapi import APIRouter

from app.models.schemas import ContainerReading

router = APIRouter()

# In-memory store for demo purposes
container_readings: dict[str, ContainerReading] = {}


@router.post("/readings")
async def receive_reading(reading: ContainerReading):
    """Receive a sensor reading from a container (IoT simulator sends data here)."""
    container_readings[reading.container_id] = reading
    from app.services.prediction import append_reading
    append_reading(reading)
    return {"status": "received", "container_id": reading.container_id}


@router.get("/readings", response_model=list[ContainerReading])
async def get_all_readings():
    """Get current readings for all containers."""
    return list(container_readings.values())


@router.get("/readings/{container_id}", response_model=ContainerReading)
async def get_reading(container_id: str):
    """Get the latest reading for a specific container."""
    if container_id not in container_readings:
        return {"error": "Container not found"}
    return container_readings[container_id]


@router.get("/critical")
async def get_critical_containers(threshold: float = 0.8):
    """Get containers above the fill threshold (default 80%)."""
    critical = [r for r in container_readings.values() if r.fill_level >= threshold]
    return {"count": len(critical), "containers": critical}
