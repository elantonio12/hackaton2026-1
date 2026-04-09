import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ContainerReading as ContainerReadingModel
from app.db.models import Sensor
from app.core.config import settings
from app.models.schemas import (
    ContainerReading,
    SensorInfo,
    SensorPayload,
    SensorRegistration,
    SensorUpdate,
)

router = APIRouter()
sensor_security = HTTPBearer()

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def verify_sensor_token(
    credentials: HTTPAuthorizationCredentials = Depends(sensor_security),
) -> str:
    if credentials.credentials != settings.sensor_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sensor invalido",
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


async def seed_sensor_registry(db: AsyncSession) -> None:
    random.seed(42)
    idx = 1
    sensors = []
    for zone_name, center in ZONES.items():
        count = CONTAINERS_PER_ZONE if zone_name != "sur" else 16
        for _ in range(count):
            container_id = f"CNT-{idx:03d}"
            sensor_id = f"SENSOR-{container_id}"
            sensors.append({
                "sensor_id": sensor_id,
                "container_id": container_id,
                "latitude": round(center["lat"] + random.uniform(-0.02, 0.02), 6),
                "longitude": round(center["lon"] + random.uniform(-0.02, 0.02), 6),
                "zone": zone_name,
            })
            idx += 1

    if sensors:
        stmt = pg_insert(Sensor).values(sensors)
        stmt = stmt.on_conflict_do_nothing(index_elements=["sensor_id"])
        await db.execute(stmt)
        await db.commit()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=SensorInfo)
async def register_sensor(
    reg: SensorRegistration,
    _token: str = Depends(verify_sensor_token),
    db: AsyncSession = Depends(get_db),
):
    data = reg.model_dump()
    stmt = pg_insert(Sensor).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sensor_id"],
        set_={k: stmt.excluded[k] for k in data if k != "sensor_id"},
    )
    await db.execute(stmt)
    await db.commit()
    return reg


@router.get("/registry", response_model=list[SensorInfo])
async def list_sensors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Sensor))
    return [s.to_dict() for s in result.scalars().all()]


@router.post("/readings")
async def receive_sensor_reading(
    payload: SensorPayload,
    _token: str = Depends(verify_sensor_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Sensor).where(Sensor.sensor_id == payload.sensor_id))
    info = result.scalar_one_or_none()
    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Sensor '{payload.sensor_id}' no registrado. "
                   f"POST /api/v1/sensors/register primero.",
        )

    reading = ContainerReading(
        container_id=info.container_id,
        latitude=info.latitude,
        longitude=info.longitude,
        fill_level=payload.fill_level,
        zone=info.zone,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Upsert into DB
    data = reading.model_dump()
    stmt = pg_insert(ContainerReadingModel).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["container_id"],
        set_={k: stmt.excluded[k] for k in data if k != "container_id"},
    )
    await db.execute(stmt)
    await db.commit()

    # In-memory prediction service
    from app.services.prediction import append_reading, maybe_retrain
    append_reading(reading)
    maybe_retrain()

    return {
        "status": "received",
        "container_id": reading.container_id,
        "fill_level": reading.fill_level,
        "height_cm": payload.height_cm,
    }

# ---------------------------------------------------------------------------
# Sensor CRUD
# ---------------------------------------------------------------------------

@router.get("/registry/{sensor_id}", response_model=SensorInfo)
async def get_sensor(sensor_id: str, db: AsyncSession = Depends(get_db)):
    """Obtener detalle de un sensor por ID."""
    result = await db.execute(select(Sensor).where(Sensor.sensor_id == sensor_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    return row.to_dict()


@router.patch("/registry/{sensor_id}", response_model=SensorInfo)
async def update_sensor(
    sensor_id: str, updates: SensorUpdate, db: AsyncSession = Depends(get_db)
):
    """Actualizar campos de un sensor (zona, coordenadas, status)."""
    result = await db.execute(select(Sensor).where(Sensor.sensor_id == sensor_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row.to_dict()


@router.delete("/registry/{sensor_id}")
async def delete_sensor(sensor_id: str, db: AsyncSession = Depends(get_db)):
    """Soft delete: desactiva el sensor sin borrar su historial."""
    result = await db.execute(select(Sensor).where(Sensor.sensor_id == sensor_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    row.activo = False
    row.status = "inactivo"
    await db.commit()
    return {"status": "deactivated", "id": sensor_id}
