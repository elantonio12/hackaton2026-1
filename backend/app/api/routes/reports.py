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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import require_admin
from app.db.database import get_db
from app.db.models import ContainerReading, ProblemReport, User
from app.models.schemas import CitizenReport as CitizenReportSchema
from app.models.schemas import CitizenReportOut

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed status transitions for ProblemReport.status. The form is open
# enough for ops triage but tight enough to prevent typos in the table.
VALID_REPORT_STATUSES = {"recibido", "en_proceso", "resuelto", "descartado"}


class ReportStatusUpdate(BaseModel):
    status: str

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
    status: str | None = None,
    problem_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return recent citizen reports, most recent first.

    Optional filters:
    - `status`: recibido | en_proceso | resuelto | descartado
    - `problem_type`: any of VALID_PROBLEM_TYPES

    Used by both the dashboard ReportList (no filters, top 10) and
    /admin/reportes (filterable, larger limit).
    """
    stmt = select(ProblemReport)
    if status:
        if status not in VALID_REPORT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Status inválido. Usa uno de: {sorted(VALID_REPORT_STATUSES)}",
            )
        stmt = stmt.where(ProblemReport.status == status)
    if problem_type:
        if problem_type not in VALID_PROBLEM_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo inválido. Usa uno de: {sorted(VALID_PROBLEM_TYPES)}",
            )
        stmt = stmt.where(ProblemReport.tipo_problema == problem_type)
    stmt = stmt.order_by(ProblemReport.timestamp.desc()).limit(limit)

    result = await db.execute(stmt)
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


@router.get("/citizen/stats")
async def get_citizen_report_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate counts of citizen reports for the admin dashboard.

    Returns totals broken down by status and problem_type so the
    /admin/reportes header strip can render at a glance.
    """
    from sqlalchemy import func

    total_q = await db.execute(select(func.count()).select_from(ProblemReport))
    total = total_q.scalar() or 0

    by_status_q = await db.execute(
        select(ProblemReport.status, func.count())
        .group_by(ProblemReport.status)
    )
    by_status: dict[str, int] = {row[0]: row[1] for row in by_status_q.all()}

    by_type_q = await db.execute(
        select(ProblemReport.tipo_problema, func.count())
        .group_by(ProblemReport.tipo_problema)
    )
    by_type: dict[str, int] = {row[0]: row[1] for row in by_type_q.all()}

    return {
        "total": total,
        "by_status": {s: by_status.get(s, 0) for s in VALID_REPORT_STATUSES},
        "by_type": by_type,
    }


@router.patch("/citizen/{report_id}/status", response_model=CitizenReportOut)
async def update_report_status(
    report_id: int,
    payload: ReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Mark a citizen report as recibido / en_proceso / resuelto / descartado.

    Admin-only. Used by /admin/reportes to triage reports without
    leaving the dashboard.
    """
    if payload.status not in VALID_REPORT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido. Usa uno de: {sorted(VALID_REPORT_STATUSES)}",
        )

    result = await db.execute(
        select(ProblemReport).where(ProblemReport.id == report_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    row.status = payload.status
    await db.commit()
    await db.refresh(row)

    logger.info(
        "[reports] %s changed report %s status -> %s",
        "admin", report_id, payload.status,
    )

    return CitizenReportOut(
        id=row.id,
        container_id=row.container_id or "—",
        zone=row.zone,
        problem_type=row.tipo_problema,
        description=row.descripcion,
        status=row.status,
        created_at=row.timestamp.isoformat(),
    )
