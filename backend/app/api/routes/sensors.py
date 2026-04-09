import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.routes.containers import container_readings
from app.core.config import settings
from app.models.schemas import (
    ContainerReading,
    SensorInfo,
    SensorPayload,
    SensorRegistration,
)

router = APIRouter()
sensor_security = HTTPBearer()

# In-memory sensor registry: sensor_id -> metadata
sensor_registry: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def verify_sensor_token(
    credentials: HTTPAuthorizationCredentials = Depends(sensor_security),
) -> str:
    """Validate that the request carries the correct sensor API key."""
    if credentials.credentials != settings.sensor_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sensor inválido",
        )
    return credentials.credentials

# ---------------------------------------------------------------------------
# Seed demo data
# ---------------------------------------------------------------------------

ZONES = {
    "centro": {"lat": 19.4326, "lon": -99.1332},
    "norte": {"lat": 19.4890, "lon": -99.1250},
    "sur": {"lat": 19.3600, "lon": -99.1560},
}
CONTAINERS_PER_ZONE = 17


def seed_sensor_registry() -> None:
    """Pre-populate registry with 50 demo sensors matching simulator containers."""
    random.seed(42)  # reproducible coordinates
    idx = 1
    for zone_name, center in ZONES.items():
        count = CONTAINERS_PER_ZONE if zone_name != "sur" else 16
        for _ in range(count):
            container_id = f"CNT-{idx:03d}"
            sensor_id = f"SENSOR-{container_id}"
            sensor_registry[sensor_id] = {
                "sensor_id": sensor_id,
                "container_id": container_id,
                "latitude": round(center["lat"] + random.uniform(-0.02, 0.02), 6),
                "longitude": round(center["lon"] + random.uniform(-0.02, 0.02), 6),
                "zone": zone_name,
            }
            idx += 1

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=SensorInfo)
async def register_sensor(
    reg: SensorRegistration,
    _token: str = Depends(verify_sensor_token),
):
    """Register a new sensor or update its location."""
    sensor_registry[reg.sensor_id] = reg.model_dump()
    return reg


@router.get("/registry", response_model=list[SensorInfo])
async def list_sensors():
    """List all registered sensors."""
    return list(sensor_registry.values())


@router.post("/readings")
async def receive_sensor_reading(
    payload: SensorPayload,
    _token: str = Depends(verify_sensor_token),
):
    """Receive a reading from a physical sensor. Requires sensor API key."""
    info = sensor_registry.get(payload.sensor_id)
    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Sensor '{payload.sensor_id}' no registrado. "
                   f"POST /api/v1/sensors/register primero.",
        )

    reading = ContainerReading(
        container_id=info["container_id"],
        latitude=info["latitude"],
        longitude=info["longitude"],
        fill_level=payload.fill_level,
        zone=info["zone"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    container_readings[reading.container_id] = reading

    from app.services.prediction import append_reading, maybe_retrain
    append_reading(reading)
    maybe_retrain()

    return {
        "status": "received",
        "container_id": reading.container_id,
        "fill_level": reading.fill_level,
        "height_cm": payload.height_cm,
    }
