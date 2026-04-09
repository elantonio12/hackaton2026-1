"""
Endpoints para el Usuario Ciudadano - EcoRuta
=============================================
GET  /api/v1/user/next-truck          → Próximo camión por zona (horario)
GET  /api/v1/user/container/{id}      → Nivel de llenado del contenedor privado
POST /api/v1/user/report              → Reportar un problema
GET  /api/v1/user/active-trucks       → Camiones activos en la zona
GET  /api/v1/user/truck-eta           → ETA del camión a un contenedor específico
"""

from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.routes.containers import container_readings
from app.api.routes.collectors import collectors_db
from app.services.prediction import predict_container
from app.services.truck_prediction import predict_truck_eta

router = APIRouter()

# ---------------------------------------------------------------------------
# Zonas válidas
# ---------------------------------------------------------------------------

VALID_ZONES = {"norte", "centro", "sur"}

# ---------------------------------------------------------------------------
# Políticas de horarios por zona (CDMX)
# Días basados en el calendario oficial SEDEMA 2026 (programa Basura Cero):
#   Orgánicos:    martes, jueves y sábado
#   Inorgánicos:  lunes, miércoles, viernes y domingo
# Horarios diferenciados por zona según densidad de recolección.
# Fuente: SEDEMA / Gobierno CDMX, enero 2026
# ---------------------------------------------------------------------------

ZONE_SCHEDULES = {
    "norte": {
        "organicos": {
            "dias": ["martes", "jueves", "sábado"],
            "hora_inicio": 7,
            "hora_fin": 13,
        },
        "inorganicos": {
            "dias": ["lunes", "miércoles", "viernes", "domingo"],
            "hora_inicio": 7,
            "hora_fin": 13,
        },
        "descripcion": (
            "Zona Norte — Orgánicos (bolsa verde): martes, jueves y sábado de 7:00 a 13:00 hrs. "
            "Inorgánicos (bolsa gris/naranja): lunes, miércoles, viernes y domingo de 7:00 a 13:00 hrs."
        ),
    },
    "centro": {
        "organicos": {
            "dias": ["martes", "jueves", "sábado"],
            "hora_inicio": 8,
            "hora_fin": 14,
        },
        "inorganicos": {
            "dias": ["lunes", "miércoles", "viernes", "domingo"],
            "hora_inicio": 8,
            "hora_fin": 14,
        },
        "descripcion": (
            "Zona Centro — Orgánicos (bolsa verde): martes, jueves y sábado de 8:00 a 14:00 hrs. "
            "Inorgánicos (bolsa gris/naranja): lunes, miércoles, viernes y domingo de 8:00 a 14:00 hrs."
        ),
    },
    "sur": {
        "organicos": {
            "dias": ["martes", "jueves", "sábado"],
            "hora_inicio": 9,
            "hora_fin": 15,
        },
        "inorganicos": {
            "dias": ["lunes", "miércoles", "viernes", "domingo"],
            "hora_inicio": 9,
            "hora_fin": 15,
        },
        "descripcion": (
            "Zona Sur — Orgánicos (bolsa verde): martes, jueves y sábado de 9:00 a 15:00 hrs. "
            "Inorgánicos (bolsa gris/naranja): lunes, miércoles, viernes y domingo de 9:00 a 15:00 hrs."
        ),
    },
}

WEEKDAY_NAMES = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo",
}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NextTruckResponse(BaseModel):
    zone: str
    tipo_residuo: str           # "organicos" o "inorganicos"
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


class ProblemReport(BaseModel):
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

def _get_next_collection(zone: str, tipo_residuo: str | None = None) -> dict:
    """
    Calcula el próximo camión de recolección para una zona.
    Si tipo_residuo es 'organicos' o 'inorganicos', filtra solo ese tipo.
    Si no se especifica, retorna el que llegue más pronto de cualquier tipo.
    """
    schedule = ZONE_SCHEDULES[zone]
    now = datetime.now(timezone.utc)
    cdmx_now = now - timedelta(hours=6)
    current_weekday = cdmx_now.weekday()
    current_hour = cdmx_now.hour
    current_day_name = WEEKDAY_NAMES[current_weekday]
    weekday_map = {v: k for k, v in WEEKDAY_NAMES.items()}

    # Filtrar por tipo si se especificó
    tipos = (
        [(tipo_residuo, schedule[tipo_residuo])]
        if tipo_residuo
        else [("organicos", schedule["organicos"]), ("inorganicos", schedule["inorganicos"])]
    )

    best = None
    best_hours = float("inf")

    for tipo, config in tipos:
        hora_inicio = config["hora_inicio"]
        hora_fin = config["hora_fin"]
        collection_days = config["dias"]

        # ¿Está en curso ahora mismo?
        if current_day_name in collection_days and hora_inicio <= current_hour < hora_fin:
            return {
                "tipo_residuo": tipo,
                "proximo_dia": current_day_name,
                "hora_inicio": f"{hora_inicio:02d}:00",
                "hora_fin": f"{hora_fin:02d}:00",
                "en_curso": True,
                "horas_para_siguiente": None,
            }

        # Buscar el más próximo
        for day_name in collection_days:
            target_weekday = weekday_map[day_name]
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0 and current_hour >= hora_fin:
                days_ahead = 7
            hours_ahead = days_ahead * 24 + (hora_inicio - current_hour)
            if hours_ahead < best_hours:
                best_hours = hours_ahead
                best = {
                    "tipo_residuo": tipo,
                    "proximo_dia": day_name,
                    "hora_inicio": f"{hora_inicio:02d}:00",
                    "hora_fin": f"{hora_fin:02d}:00",
                    "en_curso": False,
                    "horas_para_siguiente": round(hours_ahead, 1),
                }

    return best


def _fill_status(fill_level: float) -> str:
    if fill_level >= 0.9:
        return "crítico"
    elif fill_level >= 0.75:
        return "alto"
    return "normal"


# ---------------------------------------------------------------------------
# Problem reports store
# ---------------------------------------------------------------------------

problem_reports: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/next-truck", response_model=NextTruckResponse)
async def get_next_truck(zone: str, tipo_residuo: str | None = None):
    """
    Retorna cuándo pasa el próximo camión de recolección por la zona.

    - zone: norte, centro o sur
    - tipo_residuo (opcional): 'organicos' o 'inorganicos'
      Si no se especifica, devuelve el camión más próximo de cualquier tipo.

    Calendario oficial SEDEMA 2026 (Basura Cero):
      Orgánicos (bolsa verde):   martes, jueves y sábado
      Inorgánicos (bolsa gris/naranja): lunes, miércoles, viernes y domingo
    """
    zone = zone.lower()
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=400,
            detail=f"Zona inválida '{zone}'. Usa: norte, centro o sur.",
        )

    if tipo_residuo is not None:
        tipo_residuo = tipo_residuo.lower()
        if tipo_residuo not in {"organicos", "inorganicos"}:
            raise HTTPException(
                status_code=400,
                detail="tipo_residuo debe ser 'organicos' o 'inorganicos'.",
            )

    schedule = ZONE_SCHEDULES[zone]
    next_collection = _get_next_collection(zone, tipo_residuo)

    return NextTruckResponse(
        zone=zone,
        descripcion=schedule["descripcion"],
        **next_collection,
    )


@router.get("/container/{container_id}", response_model=ContainerStatusResponse)
async def get_container_status(container_id: str):
    """
    Retorna el nivel de llenado actual del contenedor privado del usuario
    más predicción de cuándo se llenará (modelo MLP).
    """
    reading = container_readings.get(container_id)
    if not reading:
        raise HTTPException(
            status_code=404,
            detail=f"Contenedor '{container_id}' no encontrado. "
                   "Verifica que el sensor esté activo y enviando datos.",
        )

    prediction = predict_container(container_id)

    return ContainerStatusResponse(
        container_id=reading.container_id,
        zone=reading.zone,
        fill_level=reading.fill_level,
        fill_level_pct=f"{reading.fill_level * 100:.1f}%",
        status=_fill_status(reading.fill_level),
        timestamp=reading.timestamp,
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
):
    """
    Predice la hora estimada de llegada (ETA) del camión a un contenedor
    específico dentro de su ruta, usando el modelo MLP de predicción de rutas.

    Parámetros:
    - container_id: ID del contenedor (ej. CNT-001)
    - stop_order: posición de la parada en la ruta (1, 2, 3...)
    - total_stops: total de paradas en la ruta
    - distance_to_stop_km: distancia acumulada desde el inicio hasta esta parada
    """
    # Obtener zona y nivel de llenado del contenedor si está disponible
    reading = container_readings.get(container_id)
    zone = reading.zone if reading else "centro"
    fill_level = reading.fill_level if reading else 0.5

    if zone not in VALID_ZONES:
        raise HTTPException(status_code=400, detail=f"Zona inválida: {zone}")

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
async def submit_problem_report(report: ProblemReport):
    """
    El usuario reporta un problema: camión que no pasó, contenedor lleno,
    contenedor dañado, mal olor, u otro.
    """
    entry = {
        **report.model_dump(),
        "id": len(problem_reports) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "recibido",
    }
    problem_reports.append(entry)

    return {
        "status": "recibido",
        "reporte_id": entry["id"],
        "mensaje": "Tu reporte fue registrado. El equipo de EcoRuta lo revisará pronto.",
        "timestamp": entry["timestamp"],
    }


@router.get("/active-trucks", response_model=ActiveTrucksResponse)
async def get_active_trucks(zone: str):
    """
    Retorna los camiones recolectores activos en la zona del usuario.
    """
    zone = zone.lower()
    if zone not in VALID_ZONES:
        raise HTTPException(
            status_code=400,
            detail=f"Zona inválida '{zone}'. Usa: norte, centro o sur.",
        )

    activos = [
        c for c in collectors_db.values()
        if c.get("zona") == zone and c.get("activo", False)
    ]

    camiones = [
        {
            "camion_id": c["camion_id"],
            "nombre_recolector": c["nombre"],
            "zona": c["zona"],
            "telefono": c.get("telefono"),
        }
        for c in activos
    ]

    return ActiveTrucksResponse(
        zone=zone,
        total_activos=len(camiones),
        camiones=camiones,
    )


@router.get("/reports")
async def get_problem_reports(zone: str | None = None):
    """Consulta los reportes de problemas. Filtrable por zona."""
    result = problem_reports
    if zone:
        result = [r for r in result if r.get("zone") == zone.lower()]
    return {"total": len(result), "reportes": result}