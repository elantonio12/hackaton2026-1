"""Simulated container definitions across 3 CDMX zones.

Each container has a GPS coordinate, zone, and initial fill level.
"""

import random

# Zone centers (approximate GPS coords in CDMX)
ZONES = {
    "centro": {"lat": 19.4326, "lon": -99.1332},
    "norte": {"lat": 19.4890, "lon": -99.1250},
    "sur": {"lat": 19.3600, "lon": -99.1560},
}

CONTAINERS_PER_ZONE = 17  # ~50 total


def _generate_containers() -> list[dict]:
    containers = []
    idx = 1
    for zone_name, center in ZONES.items():
        count = CONTAINERS_PER_ZONE if zone_name != "sur" else 16
        for _ in range(count):
            containers.append({
                "id": f"CNT-{idx:03d}",
                "latitude": round(center["lat"] + random.uniform(-0.02, 0.02), 6),
                "longitude": round(center["lon"] + random.uniform(-0.02, 0.02), 6),
                "zone": zone_name,
                "fill_level": round(random.uniform(0.05, 0.65), 3),
            })
            idx += 1
    return containers


CONTAINERS = _generate_containers()
