"""HTTP client for the self-hosted OSRM router.

Wraps the two endpoints we care about:
  - /route/v1/driving  -> ordered routing with full polyline geometry
  - /table/v1/driving  -> distance/duration matrix for VRP solving

The base URL is taken from the OSRM_URL env var (defaults to the
docker-compose service name `http://osrm:5000`). All requests are
synchronous httpx calls — they're cheap and the VRP solver is itself
synchronous, so there's no benefit to making this async right now.
"""
from __future__ import annotations

import logging
import os
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

OSRM_URL = os.environ.get("OSRM_URL", "http://osrm:5000")
HTTP_TIMEOUT = float(os.environ.get("OSRM_TIMEOUT", "30"))


class OSRMError(RuntimeError):
    """Raised when OSRM returns a non-Ok status code or unreachable."""


def _coords_to_string(coords: Sequence[tuple[float, float]]) -> str:
    """Convert [(lat, lon), ...] to OSRM's `lon,lat;lon,lat;...` format."""
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)


def get_route(
    coords: Sequence[tuple[float, float]],
    *,
    overview: str = "full",
    geometries: str = "geojson",
) -> dict:
    """Compute an ordered driving route through `coords` (list of (lat, lon)).

    Returns a dict with:
      - distance_m: total distance in meters
      - duration_s: total duration in seconds
      - geometry: GeoJSON LineString {"type":"LineString","coordinates":[[lon,lat],...]}
      - legs: list of {distance, duration} per consecutive pair of waypoints
    """
    if len(coords) < 2:
        raise OSRMError("get_route requires at least 2 coordinates")

    url = f"{OSRM_URL}/route/v1/driving/{_coords_to_string(coords)}"
    params = {
        "overview": overview,
        "geometries": geometries,
        "steps": "false",
        "annotations": "false",
    }
    try:
        r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise OSRMError(f"OSRM /route failed: {exc}") from exc

    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise OSRMError(f"OSRM /route returned no route: {data.get('code')}")

    route = data["routes"][0]
    return {
        "distance_m": float(route["distance"]),
        "duration_s": float(route["duration"]),
        "geometry": route["geometry"],
        "legs": [
            {"distance": leg["distance"], "duration": leg["duration"]}
            for leg in route.get("legs", [])
        ],
    }


def get_table(
    coords: Sequence[tuple[float, float]],
    *,
    annotations: str = "duration,distance",
) -> dict:
    """Get a NxN driving distance/duration matrix for `coords`.

    Returns a dict with:
      - durations: list[list[float]] in seconds
      - distances: list[list[float]] in meters
    """
    if len(coords) < 2:
        raise OSRMError("get_table requires at least 2 coordinates")

    url = f"{OSRM_URL}/table/v1/driving/{_coords_to_string(coords)}"
    params = {"annotations": annotations}
    try:
        r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise OSRMError(f"OSRM /table failed: {exc}") from exc

    data = r.json()
    if data.get("code") != "Ok":
        raise OSRMError(f"OSRM /table failed: {data.get('code')}")

    return {
        "durations": data.get("durations") or [],
        "distances": data.get("distances") or [],
    }


def is_available() -> bool:
    """Lightweight liveness check (used at startup so we degrade gracefully
    when OSRM is still preprocessing the routing graph)."""
    try:
        # Random central CDMX coordinate — only used to ping the API
        r = httpx.get(
            f"{OSRM_URL}/route/v1/driving/-99.1332,19.4326;-99.1330,19.4328",
            params={"overview": "false"},
            timeout=2.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False
