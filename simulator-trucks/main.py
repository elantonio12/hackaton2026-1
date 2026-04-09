"""Truck fleet simulator.

Mirrors the design of simulator/main.py for sensors but for the operational
truck fleet:
  - Single async loop, one tick every TICK_SECONDS.
  - Each tick: poll backend for the canonical truck list, update local
    state, advance each en_route truck along its polyline, post location
    updates and collection events back to the backend.
  - Demo speed multiplier so the trucks visibly move on the dashboard
    map even though real garbage trucks crawl at 20-30 km/h.

Authentication: same shared sensor token used by the IoT sensor simulator.

Bootstrapping: on startup the simulator triggers an initial /routes/optimize
call (with admin credentials) so the demo isn't blank for the first tick.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Optional

import httpx

from .truck import Truck

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("truck-sim")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
SENSOR_TOKEN = os.environ.get("SENSOR_API_KEY", "ecoruta-sensor-secret-2026")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@ecoruta.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "5"))
BASE_SPEED_KMH = float(os.environ.get("BASE_SPEED_KMH", "30"))
DEMO_SPEED_MULT = float(os.environ.get("DEMO_SPEED_MULT", "8"))
COLLECTION_TICKS = int(os.environ.get("COLLECTION_TICKS", "2"))  # ticks spent at each stop

# Effective speed in m/tick
SPEED_M_PER_TICK = (BASE_SPEED_KMH * DEMO_SPEED_MULT) * 1000.0 / 3600.0 * TICK_SECONDS


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def sensor_headers() -> dict:
    return {"Authorization": f"Bearer {SENSOR_TOKEN}", "Content-Type": "application/json"}


async def fetch_truck_list(client: httpx.AsyncClient) -> list[dict]:
    try:
        r = await client.get(f"{BACKEND_URL}/api/v1/trucks/")
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        log.warning("[fetch_trucks] %s", exc)
        return []


async def fetch_route(client: httpx.AsyncClient, truck_id: str) -> Optional[dict]:
    try:
        r = await client.get(f"{BACKEND_URL}/api/v1/trucks/{truck_id}/route")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        log.debug("[fetch_route] %s for %s", exc, truck_id)
        return None


async def post_location(client: httpx.AsyncClient, truck: Truck) -> None:
    payload = {
        "latitude": truck.current_lat,
        "longitude": truck.current_lon,
        "status": truck.status,
        "current_load_m3": truck.current_load_m3,
        "current_route_id": truck.current_route_id,
    }
    try:
        await client.post(
            f"{BACKEND_URL}/api/v1/trucks/{truck.id}/location",
            json=payload,
            headers=sensor_headers(),
        )
    except httpx.HTTPError as exc:
        log.debug("[post_location] %s for %s", exc, truck.id)


async def post_collection(client: httpx.AsyncClient, truck_id: str, container_id: str) -> None:
    try:
        await client.post(
            f"{BACKEND_URL}/api/v1/trucks/{truck_id}/collect/{container_id}",
            headers=sensor_headers(),
        )
    except httpx.HTTPError as exc:
        log.warning("[post_collection] %s for %s/%s", exc, truck_id, container_id)


async def post_route_complete(client: httpx.AsyncClient, truck_id: str) -> None:
    try:
        await client.post(
            f"{BACKEND_URL}/api/v1/trucks/{truck_id}/route/complete",
            headers=sensor_headers(),
        )
    except httpx.HTTPError as exc:
        log.warning("[post_route_complete] %s for %s", exc, truck_id)


async def trigger_optimize(client: httpx.AsyncClient) -> None:
    """Login as admin once and POST /routes/optimize. Used at startup
    so the demo has routes to show before the first dashboard refresh."""
    try:
        login = await client.post(
            f"{BACKEND_URL}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        r = await client.post(
            f"{BACKEND_URL}/api/v1/routes/optimize",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if r.status_code == 200:
            log.info("[bootstrap] /routes/optimize -> %s", r.json())
        else:
            log.warning("[bootstrap] /routes/optimize HTTP %s: %s", r.status_code, r.text[:200])
    except httpx.HTTPError as exc:
        log.warning("[bootstrap] could not optimize on startup: %s", exc)


# ---------------------------------------------------------------------------
# Tick logic
# ---------------------------------------------------------------------------

async def tick(client: httpx.AsyncClient, fleet: dict[str, Truck], tick_number: int) -> None:
    """One simulation tick across the entire fleet."""
    # 1. Sync any new trucks (or status changes) from backend
    backend_trucks = await fetch_truck_list(client)
    for bt in backend_trucks:
        local = fleet.get(bt["id"])
        if not local:
            local = Truck(
                id=bt["id"],
                name=bt["name"],
                depot_lat=bt["depot_lat"],
                depot_lon=bt["depot_lon"],
                capacity_m3=bt["capacity_m3"],
                current_lat=bt["current_lat"],
                current_lon=bt["current_lon"],
                current_load_m3=bt["current_load_m3"],
                status=bt["status"],
                current_route_id=bt.get("current_route_id"),
            )
            fleet[bt["id"]] = local
            log.info("[fleet] picked up %s (%s)", local.id, local.name)
        else:
            # If backend says we have a route but locally we don't, fetch it
            if bt.get("current_route_id") and not local.polyline:
                route = await fetch_route(client, local.id)
                if route:
                    local.assign_route(
                        route_id=route["id"],
                        polyline_geojson=route["polyline_geojson"],
                        stops_payload=route["stops"],
                    )
                    log.info(
                        "[fleet] %s picked up route %s with %d stops (%.1f km)",
                        local.id, route["id"], len(route["stops"]), route["distance_km"],
                    )

    # 2. Advance each truck's state machine
    for truck in fleet.values():
        await advance_truck(client, truck, tick_number)


async def advance_truck(client: httpx.AsyncClient, truck: Truck, tick_number: int) -> None:
    if truck.status == "idle":
        # Nothing to do — backend will assign a route eventually
        await post_location(client, truck)
        return

    if truck.status == "collecting":
        if tick_number >= truck.collecting_until_tick:
            # Done collecting — load up and continue
            stop = truck.stops[truck.next_stop_index]
            truck.current_load_m3 += 1.0  # 1 m3 per container
            await post_collection(client, truck.id, stop.container_id)
            log.info(
                "[truck] %s collected %s (%d/%d)",
                truck.id, stop.container_id,
                truck.next_stop_index + 1, len(truck.stops),
            )
            truck.next_stop_index += 1

            # Capacity check — if full, head back to depot
            if truck.current_load_m3 >= truck.capacity_m3 * 0.95:
                truck.status = "returning"
                log.info(
                    "[truck] %s capacity reached (%.1f/%.1f m3), returning to depot",
                    truck.id, truck.current_load_m3, truck.capacity_m3,
                )
            else:
                truck.status = "en_route"
        await post_location(client, truck)
        return

    if truck.status in ("en_route", "returning"):
        truck.advance(SPEED_M_PER_TICK)

        # Did we just reach a pending stop?
        if truck.status == "en_route":
            stop = truck.reached_next_stop()
            if stop:
                truck.status = "collecting"
                truck.collecting_until_tick = tick_number + COLLECTION_TICKS
                truck.current_lat = stop.latitude
                truck.current_lon = stop.longitude
                log.info("[truck] %s arrived at %s, collecting...", truck.id, stop.container_id)

        # Did we reach the end of the polyline?
        if truck.reached_polyline_end():
            log.info("[truck] %s reached end of route, marking complete", truck.id)
            await post_route_complete(client, truck.id)
            truck.reset_to_depot()

        await post_location(client, truck)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def main() -> None:
    log.info(
        "[boot] BACKEND_URL=%s TICK=%.1fs SPEED=%.0f km/h (x%.1f) -> %.0f m/tick",
        BACKEND_URL, TICK_SECONDS, BASE_SPEED_KMH, DEMO_SPEED_MULT, SPEED_M_PER_TICK,
    )

    fleet: dict[str, Truck] = {}
    tick_number = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Wait for backend to be reachable
        for attempt in range(20):
            try:
                r = await client.get(f"{BACKEND_URL}/health")
                if r.status_code == 200:
                    log.info("[boot] backend is up")
                    break
            except httpx.HTTPError:
                pass
            log.info("[boot] waiting for backend... (attempt %d)", attempt + 1)
            await asyncio.sleep(5)

        # Trigger an initial optimize so the dashboard isn't blank
        await asyncio.sleep(2)  # let backend finish bootstrapping (model training, seeds)
        await trigger_optimize(client)

        # Main loop
        while True:
            tick_number += 1
            try:
                await tick(client, fleet, tick_number)
            except Exception as exc:
                log.exception("[tick] error: %s", exc)
            await asyncio.sleep(TICK_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
