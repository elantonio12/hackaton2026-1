"""Container definitions — distributed across CDMX alcaldías.

Container count is configurable via the NUM_CONTAINERS env var.
Defaults to 50 for local dev (fast startup), but production uses
10,000 across all 16 alcaldías weighted by population.
"""

import os

from simulator.cdmx_data import generate_containers


NUM_CONTAINERS = int(os.environ.get("NUM_CONTAINERS", "50"))

CONTAINERS: list[dict] = generate_containers(NUM_CONTAINERS)
