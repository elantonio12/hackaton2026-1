"""Trucks router.

Two audiences:
  - Frontend (admin dashboard, recolector view): GET endpoints to list
    trucks and read the active route assigned to a truck.
  - Truck simulator: POST endpoints to update truck location, mark a
    container as collected, and notify the backend that a route is done.

The simulator authenticates with the same shared sensor token (Bearer)
used by the IoT sensors. The frontend uses regular JWT auth.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user
from app.api.routes.sensors import verify_sensor_token
from app.db.database import get_db
from app.db.models import ContainerReading, Route, Truck, User
from app.models.schemas import (
    ActiveRouteOut,
    TruckLocationUpdate,
    TruckOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Read endpoints (frontend)
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[TruckOut])
async def list_trucks(
    zone: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all trucks. Optionally filter by zone."""
    stmt = select(Truck)
    if zone:
        stmt = stmt.where(Truck.zone == zone)
    result = await db.execute(stmt)
    trucks = result.scalars().all()
    return [_truck_payload(t) for t in trucks]


@router.get("/me/route", response_model=ActiveRouteOut)
async def get_my_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the active route for the truck assigned to the current user.

    The recolector frontend calls this from /recolector/ruta and
    /recolector/mapa to render its assigned stops and polyline.
    """
    stmt = select(Truck).where(Truck.assigned_user_sub == user.sub)
    result = await db.execute(stmt)
    truck = result.scalar_one_or_none()
    if not truck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un camion asignado. Contacta a tu supervisor.",
        )
    if not truck.current_route_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay ruta activa para tu camion en este momento.",
        )

    route = await _get_route(db, truck.current_route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return _route_payload(route)


@router.get("/me", response_model=TruckOut)
async def get_my_truck(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the truck assigned to the current authenticated user.

    Used by the recolector frontend to display the truck identity, status,
    and live position even when there is no active route (e.g. truck is
    idle at the depot between optimization rounds). The /me/route endpoint
    above 404s in that case, so this endpoint is the always-on identity
    lookup for the logged-in collector.
    """
    stmt = select(Truck).where(Truck.assigned_user_sub == user.sub)
    truck = (await db.execute(stmt)).scalar_one_or_none()
    if not truck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un camion asignado. Contacta a tu supervisor.",
        )
    return _truck_payload(truck)


@router.get("/{truck_id}", response_model=TruckOut)
async def get_truck(truck_id: str, db: AsyncSession = Depends(get_db)):
    truck = await _get_truck(db, truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Camion no encontrado")
    return _truck_payload(truck)


@router.get("/{truck_id}/route", response_model=ActiveRouteOut)
async def get_truck_route(truck_id: str, db: AsyncSession = Depends(get_db)):
    truck = await _get_truck(db, truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Camion no encontrado")
    if not truck.current_route_id:
        raise HTTPException(status_code=404, detail="El camion no tiene ruta activa")
    route = await _get_route(db, truck.current_route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return _route_payload(route)


# ---------------------------------------------------------------------------
# Write endpoints (truck simulator)
# ---------------------------------------------------------------------------

@router.post("/{truck_id}/location")
async def update_truck_location(
    truck_id: str,
    payload: TruckLocationUpdate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_sensor_token),
):
    """Truck simulator pings its current GPS position every few seconds.

    Authenticated with the shared sensor Bearer token (sensor_api_key)
    so it's a separate trust boundary from the user-facing JWT.
    """
    truck = await _get_truck(db, truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Camion no encontrado")

    truck.current_lat = payload.latitude
    truck.current_lon = payload.longitude
    if payload.status is not None:
        truck.status = payload.status
    if payload.current_load_m3 is not None:
        truck.current_load_m3 = payload.current_load_m3
    if payload.current_route_id is not None:
        truck.current_route_id = payload.current_route_id
    truck.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"status": "ok"}


@router.post("/{truck_id}/collect/{container_id}")
async def report_collection(
    truck_id: str,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_sensor_token),
):
    """The truck simulator reports it just emptied a container.

    Effects:
      1. Reset the container's fill_level to a low random-ish value
         (simulates an emptied container).
      2. Mark the corresponding stop in the active route as "collected".
    """
    truck = await _get_truck(db, truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Camion no encontrado")

    # 1) reset container fill (use 0.05 — emptied but not perfectly clean)
    cr = await db.execute(
        select(ContainerReading).where(ContainerReading.container_id == container_id)
    )
    reading = cr.scalar_one_or_none()
    if reading is not None:
        reading.fill_level = 0.05
        reading.timestamp = datetime.now(timezone.utc).isoformat()

    # 2) mark stop as collected in the active route
    if truck.current_route_id:
        route = await _get_route(db, truck.current_route_id)
        if route:
            updated_stops = []
            for stop in (route.stops or []):
                if stop.get("container_id") == container_id and stop.get("status") == "pending":
                    stop = {**stop, "status": "collected"}
                updated_stops.append(stop)
            route.stops = updated_stops

    await db.commit()
    return {"status": "ok"}


@router.post("/{truck_id}/route/complete")
async def complete_route(
    truck_id: str,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_sensor_token),
):
    """Truck finished its current route (returned to depot, dumped load).

    Sets the route status to `completed`, clears the truck's current_route_id,
    and resets its load.
    """
    truck = await _get_truck(db, truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Camion no encontrado")

    if truck.current_route_id:
        route = await _get_route(db, truck.current_route_id)
        if route:
            route.status = "completed"
            route.completed_at = datetime.now(timezone.utc)

    truck.current_route_id = None
    truck.current_load_m3 = 0.0
    truck.status = "idle"
    truck.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_truck(db: AsyncSession, truck_id: str) -> Optional[Truck]:
    result = await db.execute(select(Truck).where(Truck.id == truck_id))
    return result.scalar_one_or_none()


async def _get_route(db: AsyncSession, route_id: int) -> Optional[Route]:
    result = await db.execute(select(Route).where(Route.id == route_id))
    return result.scalar_one_or_none()


def _truck_payload(t: Truck) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "zone": t.zone,
        "capacity_m3": t.capacity_m3,
        "current_load_m3": t.current_load_m3,
        "depot_lat": t.depot_lat,
        "depot_lon": t.depot_lon,
        "current_lat": t.current_lat,
        "current_lon": t.current_lon,
        "status": t.status,
        "current_route_id": t.current_route_id,
        "updated_at": t.updated_at.isoformat() if isinstance(t.updated_at, datetime) else str(t.updated_at),
    }


def _route_payload(r: Route) -> dict:
    return {
        "id": r.id,
        "truck_id": r.truck_id,
        "stops": r.stops or [],
        "polyline_geojson": r.polyline_geojson or {"type": "LineString", "coordinates": []},
        "distance_km": r.distance_km,
        "duration_min": r.duration_min,
        "status": r.status,
        "started_at": r.started_at.isoformat() if isinstance(r.started_at, datetime) else str(r.started_at),
        "completed_at": (
            r.completed_at.isoformat()
            if isinstance(r.completed_at, datetime)
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Initial fleet seeding
# ---------------------------------------------------------------------------

DEFAULT_RECOLECTOR_PASSWORD = "recolector123"


async def seed_truck_fleet(db: AsyncSession) -> None:
    """Insert the operational truck fleet + their assigned users on startup.

    Uses backend.app.data.fleet_data.generate_fleet() — 30 trucks distributed
    across the 16 CDMX alcaldias proportionally to population. Each truck
    has a corresponding User row (role=collector) so the recolector can log
    in and the /trucks/me/route endpoint can resolve the truck via
    Truck.assigned_user_sub.

    Idempotent: ON CONFLICT DO NOTHING on both the trucks and users tables.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.api.routes.auth import _hash_password
    from app.data.fleet_data import generate_fleet

    fleet = generate_fleet()

    # ----- 1. Seed users (recolector role) -----
    user_rows = [
        {
            "sub": t.user_sub,
            "email": t.user_email,
            "name": t.user_name,
            "picture": None,
            "role": "collector",
            "provider": "seed",
            "email_verified": True,
            "password_hash": _hash_password(DEFAULT_RECOLECTOR_PASSWORD),
        }
        for t in fleet
    ]
    user_stmt = pg_insert(User).values(user_rows).on_conflict_do_nothing(index_elements=["sub"])
    await db.execute(user_stmt)

    # ----- 2. Seed trucks (assigned to those users) -----
    truck_rows = [
        {
            "id": t.id,
            "name": t.name,
            "zone": t.zone,
            "capacity_m3": t.capacity_m3,
            "current_load_m3": 0.0,
            "depot_lat": t.depot_lat,
            "depot_lon": t.depot_lon,
            "current_lat": t.depot_lat,
            "current_lon": t.depot_lon,
            "status": "idle",
            "assigned_user_sub": t.user_sub,
        }
        for t in fleet
    ]
    truck_stmt = pg_insert(Truck).values(truck_rows).on_conflict_do_nothing(index_elements=["id"])
    await db.execute(truck_stmt)

    await db.commit()
    logger.info(
        "[trucks] Seeded %d trucks and %d recolector users across %d alcaldias",
        len(truck_rows), len(user_rows),
        len({t.zone for t in fleet}),
    )
