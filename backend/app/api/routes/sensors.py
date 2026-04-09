import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import require_admin
from app.data.cdmx_data import generate_containers
from app.db.database import get_db
from app.db.models import ContainerReading as ContainerReadingModel
from app.db.models import Sensor, User
from app.core.config import settings
from app.models.schemas import (
    ContainerReading,
    SensorInfo,
    SensorPayload,
    SensorRegistration,
    SensorUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()
sensor_security = HTTPBearer()

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def verify_sensor_token(
    credentials: HTTPAuthorizationCredentials = Depends(sensor_security),
) -> str:
    # Fall back when CI-generated .env has SENSOR_API_KEY= without a value
    # (pydantic assigns "" instead of the Settings default in that case).
    expected = settings.sensor_api_key or "ecoruta-sensor-secret-2026"
    if credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sensor invalido",
        )
    return credentials.credentials


async def verify_sensor_or_admin(
    credentials: HTTPAuthorizationCredentials = Depends(sensor_security),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Hybrid auth: accept either the sensor api key OR a valid admin JWT.

    Used by sensor registration endpoints so the dashboard can create
    sensors via the same path the simulator uses, without giving the
    dashboard the shared sensor secret.
    """
    expected = settings.sensor_api_key or "ecoruta-sensor-secret-2026"
    token = credentials.credentials
    if token == expected:
        return "sensor"

    # Try as JWT admin
    from app.api.routes.auth import _decode_jwt
    try:
        payload = _decode_jwt(token)
        sub = payload.get("sub")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido (no es sensor ni admin)",
        )

    result = await db.execute(select(User).where(User.sub == sub))
    user = result.scalar_one_or_none()
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    return "admin"

# ---------------------------------------------------------------------------
# Seed demo data — CDMX alcaldías
# ---------------------------------------------------------------------------

# Match the simulator's scale. The simulator in simulator/sensors/container.py
# also reads NUM_CONTAINERS and uses the same generator, so both agree on
# the exact same container IDs, coordinates, and alcaldías.
SEED_SENSOR_COUNT = int(os.environ.get("SEED_SENSOR_COUNT", "10000"))

# Insert sensors in chunks to avoid oversized parameter lists in asyncpg.
_SEED_CHUNK_SIZE = 1000


async def seed_sensor_registry(db: AsyncSession) -> None:
    """Populate the sensors table with one entry per simulated container.

    Uses the shared cdmx_data.generate_containers() with seed=42 so the
    resulting IDs and coordinates match exactly what the simulator posts.
    """
    containers = generate_containers(SEED_SENSOR_COUNT)

    rows = [
        {
            "sensor_id": f"SENSOR-{c['id']}",
            "container_id": c["id"],
            "latitude": c["latitude"],
            "longitude": c["longitude"],
            "zone": c["zone"],
        }
        for c in containers
    ]

    inserted = 0
    for i in range(0, len(rows), _SEED_CHUNK_SIZE):
        chunk = rows[i:i + _SEED_CHUNK_SIZE]
        stmt = pg_insert(Sensor).values(chunk)
        stmt = stmt.on_conflict_do_nothing(index_elements=["sensor_id"])
        await db.execute(stmt)
        inserted += len(chunk)
    await db.commit()
    logger.info("[sensors] Seed registry: %d sensors across CDMX alcaldías", inserted)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=SensorInfo)
async def register_sensor(
    reg: SensorRegistration,
    _auth: str = Depends(verify_sensor_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """Register or upsert a sensor. Admin (via JWT) and the simulator
    (via sensor api key) both share this endpoint.

    The `zone` field is always derived from the coordinates via
    point-in-polygon — even if the caller provided a value. This way
    we have a single source of truth and the admin UI doesn't have to
    pick a zone manually. If the point is outside CDMX, 422.
    """
    from app.services.geo import find_alcaldia

    actual_zone = find_alcaldia(reg.latitude, reg.longitude)
    if actual_zone is None:
        raise HTTPException(
            status_code=422,
            detail="Las coordenadas estan fuera de la Ciudad de Mexico",
        )

    # Always use the polygon-derived zone, ignoring any value the
    # caller may have sent.
    data = reg.model_dump()
    data["zone"] = actual_zone

    stmt = pg_insert(Sensor).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sensor_id"],
        set_={k: stmt.excluded[k] for k in data if k != "sensor_id"},
    )
    await db.execute(stmt)
    await db.commit()
    # Echo back the actual zone we stored so the caller knows
    return {**data}


@router.get("/registry", response_model=list[SensorInfo])
async def list_sensors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Sensor))
    return [s.to_dict() for s in result.scalars().all()]


@router.get("/recent-collections")
async def list_recent_collections(since_ts: float = 0.0):
    """Return container_ids the trucks have collected since `since_ts`.

    The IoT sensor simulator polls this endpoint each cycle so it can
    reset the local fill_level for any container that was just emptied
    by a truck. Without this sync, the simulator's in-memory state
    keeps posting the pre-collection fill level (e.g. 0.85) and
    immediately overwrites the 0.05 reset that /trucks/{id}/collect
    wrote to the DB.

    Public (no auth): the response is just container ids and
    timestamps, no PII or sensitive data. The buffer auto-evicts
    after 10 minutes so it stays bounded.
    """
    from app.services.collections_buffer import recent_collections
    return {
        "since_ts": since_ts,
        "now_ts": __import__("time").time(),
        "collections": recent_collections.since(since_ts),
    }


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
    sensor_id: str,
    updates: SensorUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
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
async def delete_sensor(
    sensor_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Soft delete: desactiva el sensor sin borrar su historial."""
    result = await db.execute(select(Sensor).where(Sensor.sensor_id == sensor_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    row.activo = False
    row.status = "inactivo"
    await db.commit()
    return {"status": "deactivated", "id": sensor_id}
