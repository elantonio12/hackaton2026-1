"""IoT Sensor Simulator — scales to tens of thousands of containers.

Simulates a large fleet of waste containers distributed across the 16
CDMX alcaldías, each with a unique IPv6 source address when deployed
on a host with an IPv6 /64 block. Readings are batched and POSTed to
the backend via a bulk ingest endpoint.

Environment variables:
    BACKEND_URL        Backend base URL (default: http://backend:8000)
    NUM_CONTAINERS     Total containers to simulate (default: 50)
    INTERVAL_SECONDS   Seconds between ingest cycles (default: 10)
    BATCH_SIZE         Readings per bulk POST (default: 500)
    IPV6_ENABLED       "true" to bind each client to an IPv6 from IPV6_PREFIX
    IPV6_PREFIX        IPv6 /64 prefix (default: 2605:a140:2302:3245::)
    IPV6_CLIENTS       Number of distinct IPv6 clients to rotate (default: 100)
"""

import asyncio
import os
import random
from datetime import datetime, timezone

import httpx

from simulator.ipv6_pool import address_for
from simulator.sensors.container import CONTAINERS


BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "10"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500"))
IPV6_ENABLED = os.environ.get("IPV6_ENABLED", "false").lower() == "true"
IPV6_PREFIX = os.environ.get("IPV6_PREFIX", "2605:a140:2302:3245::")
# Number of distinct IPv6 source clients to rotate through. Creating one
# transport per sensor is expensive at 10K scale, so we use a pool.
IPV6_CLIENTS = int(os.environ.get("IPV6_CLIENTS", "100"))

BULK_ENDPOINT = f"{BACKEND_URL}/api/v1/containers/readings/bulk"
SINGLE_ENDPOINT = f"{BACKEND_URL}/api/v1/containers/readings"


def _advance_fill_level(container: dict) -> None:
    """Simulate gradual filling; reset after collection event."""
    fill = container["fill_level"] + random.uniform(0.005, 0.025)
    if fill > 1.0:
        fill = random.uniform(0.05, 0.20)
    container["fill_level"] = round(fill, 3)


def _reading_payload(container: dict) -> dict:
    return {
        "container_id": container["id"],
        "latitude": container["latitude"],
        "longitude": container["longitude"],
        "fill_level": container["fill_level"],
        "zone": container["zone"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _build_clients() -> list[httpx.AsyncClient]:
    """Build a pool of async clients.

    If IPV6_ENABLED, each client binds to a distinct IPv6 source address
    derived from a synthetic identifier. This lets the kernel route
    outbound packets from the full /64 block, simulating real IoT
    deployments where each sensor has its own network identity.
    """
    if not IPV6_ENABLED:
        return [httpx.AsyncClient(timeout=10.0)]

    clients: list[httpx.AsyncClient] = []
    for i in range(IPV6_CLIENTS):
        src_addr = address_for(f"SENSOR-POOL-{i:05d}", prefix=IPV6_PREFIX)
        transport = httpx.AsyncHTTPTransport(local_address=src_addr)
        clients.append(httpx.AsyncClient(transport=transport, timeout=10.0))
    return clients


async def _send_batch(
    client: httpx.AsyncClient,
    batch: list[dict],
    use_bulk: bool = True,
) -> tuple[bool, int]:
    """POST a batch of readings. Returns (success, count)."""
    payloads = [_reading_payload(c) for c in batch]
    try:
        if use_bulk:
            resp = await client.post(BULK_ENDPOINT, json=payloads)
        else:
            # Legacy path: single POST per reading (used only if bulk fails)
            for p in payloads:
                await client.post(SINGLE_ENDPOINT, json=p)
            return True, len(payloads)
        if resp.status_code >= 400:
            return False, 0
        return True, len(payloads)
    except httpx.ConnectError:
        return False, 0
    except Exception as e:
        print(f"[WARN] batch error: {e}")
        return False, 0


async def main() -> None:
    total = len(CONTAINERS)
    print(f"[simulator] Starting with {total} containers")
    print(f"[simulator] Backend: {BACKEND_URL}")
    print(f"[simulator] Batch size: {BATCH_SIZE}, interval: {INTERVAL_SECONDS}s")
    if IPV6_ENABLED:
        print(f"[simulator] IPv6 enabled, pool of {IPV6_CLIENTS} source clients in {IPV6_PREFIX}/64")
    else:
        print(f"[simulator] IPv6 disabled (dev mode)")

    clients = _build_clients()
    try:
        cycle = 0
        while True:
            cycle += 1
            # Update fill levels
            for c in CONTAINERS:
                _advance_fill_level(c)

            # Group into batches
            batches = [
                CONTAINERS[i:i + BATCH_SIZE]
                for i in range(0, total, BATCH_SIZE)
            ]

            # Round-robin batches across the client pool for IPv6 rotation
            tasks = [
                _send_batch(clients[i % len(clients)], batch, use_bulk=True)
                for i, batch in enumerate(batches)
            ]
            results = await asyncio.gather(*tasks)
            sent = sum(cnt for ok, cnt in results if ok)
            failed = sum(1 for ok, _ in results if not ok)

            ts = datetime.now(timezone.utc).isoformat()
            if failed:
                print(f"[{ts}] cycle {cycle}: sent {sent}/{total} ({failed} batches failed)")
            else:
                print(f"[{ts}] cycle {cycle}: sent {sent}/{total} across {len(batches)} batches")

            await asyncio.sleep(INTERVAL_SECONDS)
    finally:
        for c in clients:
            await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
