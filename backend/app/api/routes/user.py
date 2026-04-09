"""
Endpoints para el Usuario Ciudadano - EcoRuta
=============================================
GET  /api/v1/user/next-truck          -> Proximo camion por zona (horario)
GET  /api/v1/user/container/{id}      -> Nivel de llenado del contenedor privado
POST /api/v1/user/report              -> Reportar un problema
GET  /api/v1/user/active-trucks       -> Camiones activos en la zona
GET  /api/v1/user/truck-eta           -> ETA del camion a un contenedor especifico
GET  /api/v1/user/reports             -> Consultar reportes de problemas
"""

from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Collector
from app.db.models import ContainerReading as ContainerReadingModel
from app.db.models import ProblemReport
from app.services.prediction import predict_container
from app.services.truck_prediction import predict_truck_eta

router = APIRouter()

# ---------------------------------------------------------------------------
# Zonas validas
# ---------------------------------------------------------------------------

VALID_ZONES = {"norte", "centro", "sur"}

# ---------------------------------------------------------------------------
# Politicas de horarios por zona (CDMX)
# ---------------------------------------------------------------------------

ZONE_SCHEDULES = {
    "norte": {
        "dias": ["lunes", "miercoles", "viernes"],
        "hora_inicio": 7,
        "hora_fin": 14,
        "descripcion": "Zona Norte: recoleccion lunes, miercoles y viernes de 7:00 a 14:00 hrs",
    },
    "centro": {
        "dias": ["martes", "jueves", "sabado"],
        "hora_inicio": 8,
        "hora_fin": 15,
        "descripcion": "Zona Centro: recoleccion martes, jueves y sabado de 8:00 a 15:00 hrs",
    },
    "sur": {
        "dias": ["lunes", "jueves"],
        "hora_inicio": 9,
        "hora_fin": 16,
        "descripcion": "Zona Sur: recoleccion lunes y jueves de 9:00 a 16:00 hrs",
    },
}

WEEKDAY_NAMES = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NextTruckResponse(BaseModel):
    zone: str
    proximo_dia: str
    hora_inicio: str
    hora_fin: str
    descripcion: str
    en_curso: bool
    horas_para_siguiente: float | None


class ContainerStatusResponse(BaseModel):
    container_id: str
    zone: str
    fill_level: float
    fill_level_pct: str
    status: str
    timestamp: str
    predicted_fill_24h: float | None
    estimated_hours_to_full: float | None
    estimated_full_at: str | None


class TruckEtaResponse(BaseModel):
    container_id: str
    zone: str
    stop_order: int
    total_stops: int
    eta_minutes_from_route_start: float
    estimated_arrival_time: str
    estimated_arrival_datetime: str
    model_trained: bool
    confidence: str


class ProblemReportRequest(BaseModel):
    container_id: str | None = None
    latitude: float
    longitude: float
    zone: Literal["norte", "centro", "sur"]
    tipo_problema: Literal[
        "camion_no_paso",
        "contenedor_lleno",
        "contenedor_danado",
        "mal_olor",
        "otro",
    ]
    descripcion: str


class ActiveTrucksResponse(BaseModel):
    zone: str
    total_activos: int
    camiones: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_next_collection(zone: str) -> dict:
    schedule = ZONE_SCHEDULES[zone]
    now = datetime.now(timezone.utc)
    cdmx_now = now - timedelta(hours=6)
    current_weekday = cdmx_now.weekday()
    current_hour = cdmx_now.hour
    current_day_name = WEEKDAY_NAMES[current_weekday]

    collection_days = schedule["dias"]
    hora_inicio = schedule["hora_inicio"]
    hora_fin = schedule["hora_fin"]

    if current_day_name in collection_days and hora_inicio <= current_hour < hora_fin:
        return {
            "proximo_dia": current_day_name,
            "hora_inicio": f"{hora_inicio:02d}:00",
            "hora_fin": f"{hora_fin:02d}:00",
            "en_curso": True,
            "horas_para_siguiente": None,
        }

    weekday_map = {v: k for k, v in WEEKDAY_NAMES.items()}
    min_hours = float("inf")
    next_day_name = None

    for day_name in collection_days:
        target_weekday = weekday_map[day_name]
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0 and current_hour >= hora_fin:
            days_ahead = 7
        hours_ahead = days_ahead * 24 + (hora_inicio - current_hour)
        if hours_ahead < min_hours:
            min_hours = hours_ahead
            next_day_name = day_name

    return {
        "proximo_dia": next_day_name,
        "hora_inicio": f"{hora_inicio:02d}:00",
        "hora_fin": f"{hora_fin:02d}:00",
        "en_curso": False,
        "horas_para_siguiente": round(min_hours, 1),
    }


def _fill_status(fill_level: float) -> str:
    if fill_level >= 0.9:
        return "critico"
    elif fill_level >= 0.75:
        return "alto"
    return "normal"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/next-truck", response_model=NextTruckResponse)
async def get_next_truck(zone: str):
    zone = zone.lower()
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=400,
            detail=f"Zona invalida '{zone}'. Usa: norte, centro o sur.",
        )

    schedule = ZONE_SCHEDULES[zone]
    next_collection = _get_next_collection(zone)

    return NextTruckResponse(
        zone=zone,
        descripcion=schedule["descripcion"],
        **next_collection,
    )


@router.get("/container/{container_id}", response_model=ContainerStatusResponse)
async def get_container_status(container_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContainerReadingModel).where(ContainerReadingModel.container_id == container_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Contenedor '{container_id}' no encontrado. "
                   "Verifica que el sensor este activo y enviando datos.",
        )

    prediction = predict_container(container_id)

    return ContainerStatusResponse(
        container_id=row.container_id,
        zone=row.zone,
        fill_level=row.fill_level,
        fill_level_pct=f"{row.fill_level * 100:.1f}%",
        status=_fill_status(row.fill_level),
        timestamp=row.timestamp,
        predicted_fill_24h=prediction["predicted_fill_24h"] if prediction else None,
        estimated_hours_to_full=prediction["estimated_hours_to_full"] if prediction else None,
        estimated_full_at=prediction["estimated_full_at"] if prediction else None,
    )


@router.get("/truck-eta", response_model=TruckEtaResponse)
async def get_truck_eta(
    container_id: str,
    stop_order: int,
    total_stops: int,
    distance_to_stop_km: float,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContainerReadingModel).where(ContainerReadingModel.container_id == container_id)
    )
    row = result.scalar_one_or_none()
    zone = row.zone if row else "centro"
    fill_level = row.fill_level if row else 0.5

    if zone not in VALID_ZONES:
        raise HTTPException(status_code=400, detail=f"Zona invalida: {zone}")

    if stop_order < 1 or stop_order > total_stops:
        raise HTTPException(
            status_code=400,
            detail="stop_order debe ser entre 1 y total_stops.",
        )

    result = predict_truck_eta(
        container_id=container_id,
        zone=zone,
        stop_order=stop_order,
        total_stops=total_stops,
        distance_to_stop_km=distance_to_stop_km,
        fill_level=fill_level,
    )

    return TruckEtaResponse(**result)


@router.post("/report")
async def submit_problem_report(
    report: ProblemReportRequest, db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    row = ProblemReport(
        container_id=report.container_id,
        latitude=report.latitude,
        longitude=report.longitude,
        zone=report.zone,
        tipo_problema=report.tipo_problema,
        descripcion=report.descripcion,
        timestamp=now,
        status="recibido",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return {
        "status": "recibido",
        "reporte_id": row.id,
        "mensaje": "Tu reporte fue registrado. El equipo de EcoRuta lo revisara pronto.",
        "timestamp": now.isoformat(),
    }


@router.get("/active-trucks", response_model=ActiveTrucksResponse)
async def get_active_trucks(zone: str, db: AsyncSession = Depends(get_db)):
    zone = zone.lower()
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=400,
            detail=f"Zona invalida '{zone}'. Usa: norte, centro o sur.",
        )

    result = await db.execute(
        select(Collector).where(Collector.zona == zone, Collector.activo == True)
    )
    activos = result.scalars().all()

    camiones = [
        {
            "camion_id": c.camion_id,
            "nombre_recolector": c.nombre,
            "zona": c.zona,
            "telefono": c.telefono,
        }
        for c in activos
    ]

    return ActiveTrucksResponse(
        zone=zone,
        total_activos=len(camiones),
        camiones=camiones,
    )


@router.get("/reports")
async def get_problem_reports(zone: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ProblemReport)
    if zone:
        stmt = stmt.where(ProblemReport.zone == zone.lower())
    result = await db.execute(stmt)
    reports = [r.to_dict() for r in result.scalars().all()]
    return {"total": len(reports), "reportes": reports}
