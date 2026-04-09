"""Container definitions — distributed across CDMX alcaldías.

Container count is configurable via the NUM_CONTAINERS env var.
Defaults to 50 for local dev (fast startup), but production uses
10,000 across all 16 alcaldías weighted by population.

The CONTAINERS dict is keyed by container id so the discovery loop
in main.py can merge in new sensors created via the admin CRUD
without losing local fill-level state.
"""

import os
import random

from simulator.cdmx_data import generate_containers


NUM_CONTAINERS = int(os.environ.get("NUM_CONTAINERS", "50"))


def _seed_initial_containers() -> dict[str, dict]:
    """Generate the initial container set keyed by id."""
    return {c["id"]: c for c in generate_containers(NUM_CONTAINERS)}


CONTAINERS: dict[str, dict] = _seed_initial_containers()


def add_container(container_id: str, latitude: float, longitude: float, zone: str) -> None:
    """Insert a new container discovered from the backend registry.
    Initial fill level is randomized in the low range so the new sensor
    doesn't pop into existence already critical."""
    if container_id in CONTAINERS:
        return
    CONTAINERS[container_id] = {
        "id": container_id,
        "latitude": latitude,
        "longitude": longitude,
        "zone": zone,
        "display_zone": zone,
        "fill_level": round(random.uniform(0.05, 0.20), 3),
    }


def remove_container(container_id: str) -> None:
    """Stop simulating a container (e.g. soft-deleted on the backend)."""
    CONTAINERS.pop(container_id, None)
