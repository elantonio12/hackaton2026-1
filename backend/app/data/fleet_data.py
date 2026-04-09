"""Fleet seed data: 30 collection trucks distributed across CDMX alcaldías.

Trucks are assigned per alcaldía proportionally to population (more
trucks where there are more containers). Each truck has:
- A deterministic ID (TRK-01 .. TRK-30)
- A depot at the alcaldía centroid (matches cdmx_data.py coords)
- An assigned user (recolector01@ecoruta.mx .. recolector30@ecoruta.mx)
  whose sub is referenced by Truck.assigned_user_sub

The seed is run idempotently on backend startup alongside the sensor
registry seed.
"""

import math
from dataclasses import dataclass

from app.data.cdmx_data import ALCALDIAS


TOTAL_TRUCKS = 30


@dataclass
class TruckSeed:
    id: str
    name: str
    zone: str                # normalized alcaldía name
    zone_display: str        # human-readable name
    depot_lat: float
    depot_lon: float
    capacity_m3: float
    user_sub: str
    user_email: str
    user_name: str
    employee_id: str


def _distribute_trucks_by_population(total: int) -> dict[str, int]:
    """Allocate trucks across alcaldías weighted by INEGI 2020 population.

    Every alcaldía gets at least 1 truck (guaranteed minimum service).
    """
    total_pop = sum(a.population for a in ALCALDIAS)
    raw = [(a, (a.population / total_pop) * total) for a in ALCALDIAS]

    # Floor allocation + guarantee minimum 1 per alcaldía
    counts: dict[str, int] = {a.name: max(1, int(math.floor(r))) for a, r in raw}

    # Distribute any remainder to the largest fractional parts
    current = sum(counts.values())
    remainder = total - current
    if remainder > 0:
        fractions = sorted(
            [(a.name, r - math.floor(r)) for a, r in raw],
            key=lambda x: x[1],
            reverse=True,
        )
        for i in range(remainder):
            counts[fractions[i % len(fractions)][0]] += 1
    elif remainder < 0:
        # We overshot (possible if minimum-1 pushes us over total).
        # Remove from smallest alcaldías first, but keep minimum of 1.
        for a in sorted(ALCALDIAS, key=lambda x: x.population):
            if remainder >= 0:
                break
            if counts[a.name] > 1:
                counts[a.name] -= 1
                remainder += 1

    return counts


def generate_fleet() -> list[TruckSeed]:
    """Return the 30-truck fleet seed, deterministic and idempotent."""
    counts = _distribute_trucks_by_population(TOTAL_TRUCKS)
    trucks: list[TruckSeed] = []
    idx = 1
    for alcaldia in ALCALDIAS:
        count = counts.get(alcaldia.name, 0)
        for n in range(1, count + 1):
            tid = f"TRK-{idx:02d}"
            trucks.append(TruckSeed(
                id=tid,
                name=f"Camión {alcaldia.display} {n}",
                zone=alcaldia.name,
                zone_display=alcaldia.display,
                depot_lat=alcaldia.lat,
                depot_lon=alcaldia.lon,
                capacity_m3=12.0,
                user_sub=f"local|recolector{idx:02d}@ecoruta.mx",
                user_email=f"recolector{idx:02d}@ecoruta.mx",
                user_name=f"Recolector {idx:02d}",
                employee_id=f"EMP-{idx:04d}",
            ))
            idx += 1
    return trucks
