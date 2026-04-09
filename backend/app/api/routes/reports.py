"""Citizen reports about specific containers.

Reports are always tied to a `container_id`, not raw coordinates. The
user's actual geolocation (`user_latitude`/`user_longitude`) is only
used to validate proximity: if the user is more than MAX_REPORT_DISTANCE_M
away from the container they claim to be reporting, the request is
rejected as spam.
"""

import math
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ContainerReading, ProblemReport
from app.models.schemas import CitizenReport as CitizenReportSchema
from app.models.schemas import CitizenReportOut

router = APIRouter()
logger = logging.getLogger(__name__)

# A citizen must be within this many meters of the container they report.
# This is deliberately generous: GPS accuracy in urban CDMX is often
# 10-30m, and a citizen might stand across the street from the container.
MAX_REPORT_DISTANCE_M = 200

VALID_PROBLEM_TYPES = {
    "desbordado",
    "dañado",
    "basura_fuera",
    "mal_olor",
    "obstruido",
    "otro",
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two lat/lon points."""
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@router.post("/citizen")
async def submit_citizen_report(
    report: CitizenReportSchema,
    db: AsyncSession = Depends(get_db),
):
    """Submit a citizen report about a specific container.

    Validation:
    - The container must exist
    - The problem_type must be in VALID_PROBLEM_TYPES
    - The user's coordinates must be within MAX_REPORT_DISTANCE_M of the
      container's coordinates (anti-spam)
    """
    if report.problem_type not in VALID_PROBLEM_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de problema inválido. Usa uno de: {sorted(VALID_PROBLEM_TYPES)}",
        )

    # Look up the container
    result = await db.execute(
        select(ContainerReading).where(ContainerReading.container_id == report.container_id)
    )
    container = result.scalar_one_or_none()
    if not container:
        raise HTTPException(
            status_code=404,
            detail=f"Contenedor '{report.container_id}' no encontrado",
        )

    # Proximity check
    distance_m = _haversine_m(
        report.user_latitude,
        report.user_longitude,
        container.latitude,
        container.longitude,
    )
    if distance_m > MAX_REPORT_DISTANCE_M:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estás a {int(distance_m)} m del contenedor. "
                f"Debes estar a menos de {MAX_REPORT_DISTANCE_M} m para reportarlo."
            ),
        )

    # Persist as ProblemReport (tracked by operations team)
    row = ProblemReport(
        container_id=container.container_id,
        latitude=container.latitude,
        longitude=container.longitude,
        zone=container.zone,
        tipo_problema=report.problem_type,
        descripcion=report.description.strip() or "(sin descripción)",
        status="recibido",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        "[reports] citizen report %s on %s (%s) at %dm",
        row.id, container.container_id, report.problem_type, int(distance_m),
    )

    return {
        "status": "received",
        "report_id": row.id,
        "container_id": container.container_id,
        "distance_m": round(distance_m, 1),
    }


@router.get("/citizen", response_model=list[CitizenReportOut])
async def get_citizen_reports(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Return recent citizen reports, most recent first."""
    result = await db.execute(
        select(ProblemReport)
        .order_by(ProblemReport.timestamp.desc())
        .limit(limit)
    )
    return [
        CitizenReportOut(
            id=r.id,
            container_id=r.container_id or "—",
            zone=r.zone,
            problem_type=r.tipo_problema,
            description=r.descripcion,
            status=r.status,
            created_at=r.timestamp.isoformat(),
        )
        for r in result.scalars().all()
    ]
