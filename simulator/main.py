"""IoT Sensor Simulator — scales to tens of thousands of containers.

Simulates a large fleet of waste containers distributed across the 16
CDMX alcaldías, each with a unique IPv6 source address when deployed
on a host with an IPv6 /64 block. Readings are batched and POSTed to
the backend via a bulk ingest endpoint.

Discovery loop: every DISCOVERY_EVERY_N_CYCLES, the simulator polls
GET /api/v1/sensors/registry, picks up any new sensors that the admin
created via the dashboard CRUD, and stops simulating sensors that were
soft-deleted (activo=False). New sensors start at a low fill level so
they don't pop into existence already critical.

Environment variables:
    BACKEND_URL              Backend base URL (default: http://backend:8000)
    NUM_CONTAINERS           Total containers to simulate (default: 50)
    INTERVAL_SECONDS         Seconds between ingest cycles (default: 10)
    BATCH_SIZE               Readings per bulk POST (default: 500)
    DISCOVERY_EVERY_N_CYCLES Run discovery every N cycles (default: 6 = 60s)
    IPV6_ENABLED             "true" to bind each client to an IPv6 from IPV6_PREFIX
    IPV6_PREFIX              IPv6 /64 prefix (default: 2605:a140:2302:3245::)
    IPV6_CLIENTS             Number of distinct IPv6 clients to rotate (default: 100)
"""

import asyncio
import os
import random
from datetime import datetime, timezone

import httpx

from simulator.ipv6_pool import address_for
from simulator.sensors.container import CONTAINERS, add_container, remove_container


BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "10"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500"))
DISCOVERY_EVERY_N_CYCLES = int(os.environ.get("DISCOVERY_EVERY_N_CYCLES", "6"))
IPV6_ENABLED = os.environ.get("IPV6_ENABLED", "false").lower() == "true"
IPV6_PREFIX = os.environ.get("IPV6_PREFIX", "2605:a140:2302:3245::")
# Number of distinct IPv6 source clients to rotate through. Creating one
# transport per sensor is expensive at 10K scale, so we use a pool.
IPV6_CLIENTS = int(os.environ.get("IPV6_CLIENTS", "100"))

BULK_ENDPOINT = f"{BACKEND_URL}/api/v1/containers/readings/bulk"
SINGLE_ENDPOINT = f"{BACKEND_URL}/api/v1/containers/readings"
REGISTRY_ENDPOINT = f"{BACKEND_URL}/api/v1/sensors/registry"
COLLECTIONS_ENDPOINT = f"{BACKEND_URL}/api/v1/sensors/recent-collections"


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


async def _sync_recent_collections(
    client: httpx.AsyncClient, since_ts: float
) -> tuple[int, float]:
    """Pull the list of containers trucks have collected since `since_ts`
    and reset the local fill_level for each so the next post cycle
    doesn't overwrite the backend's reset.

    Returns (reset_count, new_since_ts) where new_since_ts is the
    server's reported now timestamp — caller passes that as `since_ts`
    next time so we don't reset the same container twice.
    """
    try:
        resp = await client.get(f"{COLLECTIONS_ENDPOINT}?since_ts={since_ts}")
        if resp.status_code != 200:
            return (0, since_ts)
        body = resp.json()
    except Exception as e:
        print(f"[collections] sync failed: {e}")
        return (0, since_ts)

    new_since = float(body.get("now_ts", since_ts))
    reset = 0
    for entry in body.get("collections", []):
        cid = entry.get("container_id")
        if cid and cid in CONTAINERS:
            # Match the truck collect semantic: emptied but not perfectly clean.
            CONTAINERS[cid]["fill_level"] = round(random.uniform(0.02, 0.08), 3)
            reset += 1
    return (reset, new_since)


async def _sync_with_registry(client: httpx.AsyncClient) -> tuple[int, int]:
    """Pull the canonical sensor list from the backend and reconcile.

    Returns (added, removed). Errors are swallowed (the simulator falls
    back to its current local set) so a transient backend hiccup never
    crashes the loop.
    """
    try:
        resp = await client.get(REGISTRY_ENDPOINT)
        if resp.status_code != 200:
            return (0, 0)
        registry = resp.json()
    except Exception as e:
        print(f"[discovery] sync failed: {e}")
        return (0, 0)

    added = 0
    backend_active_ids: set[str] = set()
    for s in registry:
        cid = s.get("container_id")
        if not cid:
            continue
        is_active = s.get("activo", True)
        if not is_active:
            if cid in CONTAINERS:
                remove_container(cid)
            continue
        backend_active_ids.add(cid)
        if cid not in CONTAINERS:
            add_container(
                container_id=cid,
                latitude=float(s["latitude"]),
                longitude=float(s["longitude"]),
                zone=s.get("zone", "unknown"),
            )
            added += 1

    # Soft-delete reactive: drop locally-known containers no longer in
    # backend's active list. (We never drop ones the backend doesn't
    # mention at all — those are likely seeded-only without a Sensor row.)
    return (added, 0)


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
    print(f"[simulator] Starting with {len(CONTAINERS)} containers")
    print(f"[simulator] Backend: {BACKEND_URL}")
    print(f"[simulator] Batch size: {BATCH_SIZE}, interval: {INTERVAL_SECONDS}s")
    print(f"[simulator] Discovery every {DISCOVERY_EVERY_N_CYCLES} cycles")
    if IPV6_ENABLED:
        print(f"[simulator] IPv6 enabled, pool of {IPV6_CLIENTS} source clients in {IPV6_PREFIX}/64")
    else:
        print(f"[simulator] IPv6 disabled (dev mode)")

    clients = _build_clients()
    try:
        # Initial sync — picks up sensors created via admin CRUD before
        # the simulator started (and lets us self-correct against the
        # backend's seed).
        added, _ = await _sync_with_registry(clients[0])
        if added > 0:
            print(f"[discovery] initial sync added {added} sensors -> {len(CONTAINERS)} total")

        # Track the last collection-sync timestamp so subsequent calls
        # only return events newer than what we already processed.
        # Start from 0 so the very first cycle picks up any collections
        # that happened while the simulator was offline.
        collections_since_ts = 0.0

        cycle = 0
        while True:
            cycle += 1

            # Periodic discovery — picks up CRUD-created sensors and
            # drops soft-deleted ones.
            if cycle % DISCOVERY_EVERY_N_CYCLES == 0:
                added, removed = await _sync_with_registry(clients[0])
                if added or removed:
                    print(f"[discovery] +{added} -{removed} -> {len(CONTAINERS)} total")

            # Sync recent truck collections BEFORE advancing fill levels.
            # This is the critical step: when a truck collected a container,
            # we have to overwrite our local state with ~0.05 BEFORE the
            # next _advance_fill_level call, otherwise we'd post the
            # pre-collection level back to the backend and undo the reset.
            reset_count, collections_since_ts = await _sync_recent_collections(
                clients[0], collections_since_ts
            )
            if reset_count > 0:
                print(f"[collections] reset {reset_count} containers locally after truck pickup")

            # Update fill levels (snapshot values() so we don't iterate
            # while the discovery loop mutates the dict).
            container_list = list(CONTAINERS.values())
            for c in container_list:
                _advance_fill_level(c)

            total = len(container_list)

            # Group into batches
            batches = [
                container_list[i:i + BATCH_SIZE]
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
