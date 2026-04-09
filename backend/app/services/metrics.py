"""Metrics service: aggregates operational, environmental, and financial KPIs."""

import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Collector, ContainerReading, Sensor
from app.models.schemas import ContainerReading as ContainerReadingSchema
from app.services.optimizer import _haversine, optimize_routes
from app.services.prediction import (
    container_history,
    predict_all,
    predictor,
    _compute_fill_rate,
)

# ---------------------------------------------------------------------------
# Constants (from entregable / hackathon assumptions)
# ---------------------------------------------------------------------------

# Diesel consumption: avg 3.5 km/liter for a waste truck
KM_PER_LITER = 3.5

# CO2 emission factor: 2.68 kg CO2 per liter of diesel
CO2_PER_LITER = 2.68

# Diesel price in MXN (avg CDMX 2026)
DIESEL_PRICE_MXN = 24.50

# Standard route: assume 30% longer than optimized (conservative estimate)
STANDARD_ROUTE_OVERHEAD = 1.30

# Average speed for time estimates (km/h)
AVG_SPEED_KMH = 30


async def compute_metrics(
    db: AsyncSession,
    num_vehicles: int = 3,
    fill_threshold: float = 0.8,
) -> dict:
    """Compute all metrics from current system state."""
    # Query from DB
    readings_result = await db.execute(select(ContainerReading))
    reading_rows = readings_result.scalars().all()
    readings = [ContainerReadingSchema(**r.to_dict()) for r in reading_rows]

    sensor_count = (await db.execute(select(func.count()).select_from(Sensor))).scalar() or 0

    collectors_result = await db.execute(select(Collector))
    collector_rows = collectors_result.scalars().all()

    # --- Efficiency ---
    route_result = optimize_routes(readings, num_vehicles, fill_threshold)
    routes = route_result.get("routes", [])

    optimized_km = sum(r.total_distance_km for r in routes)
    standard_km = round(optimized_km * STANDARD_ROUTE_OVERHEAD, 2)
    saved_km = round(standard_km - optimized_km, 2)
    reduction_pct = round((saved_km / standard_km * 100) if standard_km > 0 else 0, 1)
    total_visited = sum(r.containers_visited for r in routes)

    efficiency = {
        "optimized_distance_km": optimized_km,
        "standard_distance_km": standard_km,
        "distance_saved_km": saved_km,
        "distance_reduction_pct": reduction_pct,
        "total_containers_visited": total_visited,
        "vehicles_used": len(routes),
    }

    # --- Environmental ---
    fuel_saved = round(saved_km / KM_PER_LITER, 2)
    co2_avoided = round(fuel_saved * CO2_PER_LITER, 2)
    fuel_cost_saved = round(fuel_saved * DIESEL_PRICE_MXN, 2)

    environmental = {
        "fuel_saved_liters": fuel_saved,
        "co2_avoided_kg": co2_avoided,
        "diesel_price_mxn": DIESEL_PRICE_MXN,
        "fuel_cost_saved_mxn": fuel_cost_saved,
    }

    # --- Financial ---
    optimized_fuel_cost = round((optimized_km / KM_PER_LITER) * DIESEL_PRICE_MXN, 2)
    standard_fuel_cost = round((standard_km / KM_PER_LITER) * DIESEL_PRICE_MXN, 2)

    financial = {
        "daily_fuel_savings_mxn": fuel_cost_saved,
        "monthly_fuel_savings_mxn": round(fuel_cost_saved * 30, 2),
        "yearly_fuel_savings_mxn": round(fuel_cost_saved * 365, 2),
        "cost_per_optimized_route_mxn": optimized_fuel_cost,
        "cost_per_standard_route_mxn": standard_fuel_cost,
    }

    # --- System status ---
    critical = [r for r in readings if r.fill_level >= fill_threshold]

    predicted_full_24h = 0
    if predictor.is_trained:
        preds = predict_all(threshold=fill_threshold)
        predicted_full_24h = sum(
            1 for p in preds
            if p.get("estimated_hours_to_full") is not None
            and p["estimated_hours_to_full"] <= 24
        )

    system = {
        "total_containers_monitored": len(readings),
        "total_sensors_registered": sensor_count,
        "total_collectors": len(collector_rows),
        "active_collectors": sum(1 for c in collector_rows if c.activo),
        "containers_critical": len(critical),
        "containers_predicted_full_24h": predicted_full_24h,
        "prediction_model_trained": predictor.is_trained,
    }

    # --- Per-zone breakdown ---
    zone_data: dict[str, list] = {}
    for r in readings:
        zone_data.setdefault(r.zone, []).append(r)

    zones = []
    for zone_name, zone_readings in sorted(zone_data.items()):
        zone_critical = [r for r in zone_readings if r.fill_level >= fill_threshold]
        avg_fill = sum(r.fill_level for r in zone_readings) / len(zone_readings)

        # Average fill rate from history
        avg_rate = 0.0
        rate_count = 0
        for r in zone_readings:
            hist = container_history.get(r.container_id)
            if hist and len(hist) >= 2:
                from app.services.prediction import HistoricalReading
                latest = hist[-1]
                rate = _compute_fill_rate(latest, hist)
                avg_rate += rate
                rate_count += 1
        if rate_count > 0:
            avg_rate /= rate_count

        zones.append({
            "zone": zone_name,
            "total_containers": len(zone_readings),
            "critical_containers": len(zone_critical),
            "avg_fill_level": round(avg_fill, 4),
            "avg_fill_rate_per_hour": round(avg_rate, 5),
        })

    return {
        "efficiency": efficiency,
        "environmental": environmental,
        "financial": financial,
        "system": system,
        "zones": zones,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
