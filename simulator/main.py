"""IoT Sensor Simulator.

Simulates 50 waste containers across 3 CDMX zones sending fill-level
readings to the backend API at regular intervals.
"""

import asyncio
import random
from datetime import datetime, timezone

import httpx

from simulator.sensors.container import CONTAINERS

API_URL = "http://backend:8000/api/v1/containers/readings"
INTERVAL_SECONDS = 10


async def send_reading(client: httpx.AsyncClient, container: dict) -> None:
    fill_level = container["fill_level"]

    # Simulate gradual filling with some randomness
    fill_level += random.uniform(0.01, 0.05)
    if fill_level > 1.0:
        fill_level = random.uniform(0.05, 0.2)  # Emptied after collection

    container["fill_level"] = round(fill_level, 3)

    payload = {
        "container_id": container["id"],
        "latitude": container["latitude"],
        "longitude": container["longitude"],
        "fill_level": container["fill_level"],
        "zone": container["zone"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await client.post(API_URL, json=payload)
    except httpx.ConnectError:
        print(f"[WARN] Backend not reachable, retrying next cycle...")


async def main() -> None:
    print(f"Starting IoT simulator with {len(CONTAINERS)} containers...")
    async with httpx.AsyncClient(timeout=5) as client:
        while True:
            tasks = [send_reading(client, c) for c in CONTAINERS]
            await asyncio.gather(*tasks)
            print(f"[{datetime.now(timezone.utc).isoformat()}] Sent {len(CONTAINERS)} readings")
            await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
