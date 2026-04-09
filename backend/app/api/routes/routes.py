"""Routes router.

Operational route generation uses:
  - OR-Tools CVRP solver (services/vrp_solver.py) — capacity-aware
  - Self-hosted OSRM (services/osrm_client.py) — real driving distances
    and street polylines

`POST /routes/optimize` is the main entry point. It looks at all currently
idle trucks and all currently critical containers, runs CVRP, persists
one Route per truck, assigns it to the truck, and returns a summary.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import require_collector_or_admin
from app.db.database import get_db
from app.db.models import ContainerReading, Route, Truck, User
from app.models.schemas import OptimizeAllResponse
from app.services import osrm_client, vrp_solver
from app.services.vrp_solver import ContainerInput, TruckInput

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/optimize", response_model=OptimizeAllResponse)
async def optimize_routes_endpoint(
    fill_threshold: float = 0.8,
    max_containers_per_truck: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_collector_or_admin),
):
    """Run CVRP for all currently idle trucks and persist new routes.

    Returns counts of generated and skipped trucks. The frontend admin
    dashboard wires this to a "Optimizar rutas" button.
    """
    # ----- 1. Pull idle trucks -----
    trucks_q = await db.execute(
        select(Truck).where(Truck.status.in_(["idle", "offline"]))
    )
    idle_trucks = trucks_q.scalars().all()
    if not idle_trucks:
        return OptimizeAllResponse(
            generated=0,
            skipped=0,
            message="No hay camiones disponibles para optimizar",
        )

    # ----- 2. Pull critical containers (> threshold) -----
    cr_q = await db.execute(
        select(ContainerReading).where(ContainerReading.fill_level >= fill_threshold)
    )
    critical = cr_q.scalars().all()
    if not critical:
        return OptimizeAllResponse(
            generated=0,
            skipped=len(idle_trucks),
            message=f"No hay contenedores criticos (>= {int(fill_threshold * 100)}%)",
        )

    # ----- 3. Cap the matrix size to keep OSRM /table responsive -----
    # OSRM is configured with --max-table-size 5000. We keep things much
    # smaller to keep latency under a second.
    max_containers = max_containers_per_truck * len(idle_trucks)
    critical_sorted = sorted(critical, key=lambda c: -c.fill_level)
    selected_containers = critical_sorted[:max_containers]

    # ----- 4. Solve CVRP -----
    truck_inputs = [
        TruckInput(
            id=t.id,
            start_lat=t.current_lat,
            start_lon=t.current_lon,
            end_lat=t.depot_lat,
            end_lon=t.depot_lon,
            capacity_m3=t.capacity_m3,
            current_load_m3=t.current_load_m3,
        )
        for t in idle_trucks
    ]
    container_inputs = [
        ContainerInput(
            container_id=c.container_id,
            latitude=c.latitude,
            longitude=c.longitude,
            fill_level=c.fill_level,
        )
        for c in selected_containers
    ]

    try:
        solutions = vrp_solver.solve(truck_inputs, container_inputs)
    except Exception as exc:
        logger.exception("[routes] VRP solver failed")
        raise HTTPException(
            status_code=503,
            detail=f"Optimizacion fallo: {exc}. Verifica que OSRM este corriendo.",
        ) from exc

    # ----- 5. Persist routes + assign to trucks -----
    truck_by_id = {t.id: t for t in idle_trucks}
    generated = 0
    for sol in solutions:
        truck = truck_by_id.get(sol.truck_id)
        if not truck:
            continue

        new_route = Route(
            truck_id=sol.truck_id,
            stops=sol.stops,
            polyline_geojson=sol.polyline_geojson,
            distance_km=sol.distance_km,
            duration_min=sol.duration_min,
            status="active",
        )
        db.add(new_route)
        await db.flush()  # populates new_route.id

        truck.current_route_id = new_route.id
        truck.status = "en_route"
        truck.updated_at = datetime.now(timezone.utc)
        generated += 1

    await db.commit()

    skipped = len(idle_trucks) - generated
    logger.info(
        "[routes] Optimized %d/%d trucks across %d critical containers",
        generated, len(idle_trucks), len(selected_containers),
    )
    return OptimizeAllResponse(
        generated=generated,
        skipped=skipped,
        message=f"Generadas {generated} rutas para {len(selected_containers)} contenedores criticos",
    )


@router.get("/health/osrm")
async def osrm_health():
    """Quick liveness probe for OSRM — used by the frontend to render a
    "OSRM ready" indicator and by ops dashboards."""
    return {"available": osrm_client.is_available()}
