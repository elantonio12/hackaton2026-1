"""Truck state machine for the simulator.

Each Truck instance represents one in-flight vehicle. The simulator's
async loop ticks every TICK_SECONDS and asks each truck to advance one
tick — moving along its assigned polyline, collecting containers as it
reaches them, and returning to the depot when full or done.

The truck holds the polyline geometry locally so we don't have to ask
the backend for it on every tick (the backend only ever serves one
polyline per route, on assignment).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    R = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class Stop:
    order: int
    container_id: str
    latitude: float
    longitude: float
    fill_level: float
    distance_along_route_m: float


@dataclass
class Truck:
    """Local mirror of a backend Truck row, plus state for interpolation."""
    id: str
    name: str
    depot_lat: float
    depot_lon: float
    capacity_m3: float

    # Live state
    current_lat: float
    current_lon: float
    current_load_m3: float = 0.0
    status: str = "idle"  # idle | en_route | collecting | returning

    # Active route
    current_route_id: Optional[int] = None
    polyline: list[list[float]] = field(default_factory=list)  # [[lon, lat], ...]
    polyline_distances: list[float] = field(default_factory=list)  # cumulative meters per vertex
    distance_traveled_m: float = 0.0
    stops: list[Stop] = field(default_factory=list)
    next_stop_index: int = 0  # index into self.stops
    collecting_until_tick: int = 0  # tick number when collection finishes

    def assign_route(self, route_id: int, polyline_geojson: dict, stops_payload: list[dict]) -> None:
        """Switch from idle to en_route with a fresh route from the backend."""
        coords = polyline_geojson.get("coordinates") or []
        self.polyline = coords
        self.polyline_distances = self._cumulative_distances(coords)
        self.distance_traveled_m = 0.0
        self.stops = [
            Stop(
                order=s["order"],
                container_id=s["container_id"],
                latitude=s["latitude"],
                longitude=s["longitude"],
                fill_level=s["fill_level"],
                distance_along_route_m=float(s.get("distance_along_route_m", 0.0)),
            )
            for s in stops_payload
        ]
        self.next_stop_index = 0
        self.current_route_id = route_id
        self.status = "en_route"

    def total_polyline_distance_m(self) -> float:
        return self.polyline_distances[-1] if self.polyline_distances else 0.0

    def advance(self, meters: float) -> None:
        """Move `meters` along the polyline. Updates current_lat/lon."""
        if not self.polyline:
            return
        self.distance_traveled_m = min(
            self.distance_traveled_m + meters,
            self.total_polyline_distance_m(),
        )
        lat, lon = self._interpolate(self.distance_traveled_m)
        self.current_lat = lat
        self.current_lon = lon

    def reached_next_stop(self) -> Optional[Stop]:
        """Return the next stop if the truck has just reached it, else None."""
        if self.next_stop_index >= len(self.stops):
            return None
        stop = self.stops[self.next_stop_index]
        if self.distance_traveled_m + 1.0 >= stop.distance_along_route_m:
            return stop
        return None

    def reached_polyline_end(self) -> bool:
        return self.distance_traveled_m + 1.0 >= self.total_polyline_distance_m()

    def reset_to_depot(self) -> None:
        self.current_lat = self.depot_lat
        self.current_lon = self.depot_lon
        self.current_load_m3 = 0.0
        self.current_route_id = None
        self.polyline = []
        self.polyline_distances = []
        self.stops = []
        self.next_stop_index = 0
        self.distance_traveled_m = 0.0
        self.status = "idle"

    # ----- internals -----

    @staticmethod
    def _cumulative_distances(coords: list[list[float]]) -> list[float]:
        """Cumulative meters from start to each vertex."""
        if not coords:
            return []
        out = [0.0]
        total = 0.0
        for i in range(len(coords) - 1):
            a, b = coords[i], coords[i + 1]
            total += haversine_m(a[1], a[0], b[1], b[0])
            out.append(total)
        return out

    def _interpolate(self, distance_m: float) -> tuple[float, float]:
        """Return (lat, lon) at `distance_m` along the polyline."""
        if not self.polyline:
            return self.current_lat, self.current_lon
        if distance_m <= 0:
            return self.polyline[0][1], self.polyline[0][0]
        total = self.total_polyline_distance_m()
        if distance_m >= total:
            return self.polyline[-1][1], self.polyline[-1][0]

        # Binary-ish search through polyline_distances
        for i in range(len(self.polyline_distances) - 1):
            d0 = self.polyline_distances[i]
            d1 = self.polyline_distances[i + 1]
            if d0 <= distance_m <= d1:
                seg_len = d1 - d0
                ratio = (distance_m - d0) / seg_len if seg_len > 0 else 0.0
                a = self.polyline[i]
                b = self.polyline[i + 1]
                lat = a[1] + (b[1] - a[1]) * ratio
                lon = a[0] + (b[0] - a[0]) * ratio
                return lat, lon
        return self.polyline[-1][1], self.polyline[-1][0]
