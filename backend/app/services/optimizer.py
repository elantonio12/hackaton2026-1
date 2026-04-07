import math

from app.models.schemas import ContainerReading, OptimizedRoute, RouteStop


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _greedy_tsp(containers: list[ContainerReading]) -> list[ContainerReading]:
    """Simple greedy nearest-neighbor TSP solver."""
    if not containers:
        return []

    visited = [containers[0]]
    remaining = containers[1:]

    while remaining:
        last = visited[-1]
        nearest = min(
            remaining,
            key=lambda c: _haversine(last.latitude, last.longitude, c.latitude, c.longitude),
        )
        visited.append(nearest)
        remaining.remove(nearest)

    return visited


def optimize_routes(
    readings: list[ContainerReading],
    num_vehicles: int,
    fill_threshold: float,
) -> dict:
    """Generate optimized routes for the given number of vehicles."""
    priority = [r for r in readings if r.fill_level >= fill_threshold]

    if not priority:
        return {"routes": [], "message": "No containers above threshold"}

    # Distribute containers across vehicles
    sorted_by_zone = sorted(priority, key=lambda c: c.zone)
    chunks = [[] for _ in range(num_vehicles)]
    for i, container in enumerate(sorted_by_zone):
        chunks[i % num_vehicles].append(container)

    routes = []
    for idx, chunk in enumerate(chunks):
        if not chunk:
            continue

        ordered = _greedy_tsp(chunk)
        total_dist = sum(
            _haversine(
                ordered[i].latitude, ordered[i].longitude,
                ordered[i + 1].latitude, ordered[i + 1].longitude,
            )
            for i in range(len(ordered) - 1)
        )

        stops = [
            RouteStop(
                container_id=c.container_id,
                latitude=c.latitude,
                longitude=c.longitude,
                fill_level=c.fill_level,
                order=i + 1,
            )
            for i, c in enumerate(ordered)
        ]

        routes.append(
            OptimizedRoute(
                vehicle_id=f"truck-{idx + 1:02d}",
                stops=stops,
                total_distance_km=round(total_dist, 2),
                estimated_time_min=round(total_dist / 30 * 60, 1),
                containers_visited=len(stops),
            )
        )

    return {"routes": routes, "total_vehicles": len(routes)}
