"""Capacitated Vehicle Routing Problem (CVRP) solver using OR-Tools.

The solver:
  1. Takes a list of trucks (each with current location, depot, capacity)
     and a list of critical containers (each with lat/lon and a "demand"
     in m3 — typically 1.0 since we model 1 m3 per full container).
  2. Asks OSRM for a driving distance matrix between all the points
     (trucks' current locations + containers + depots).
  3. Solves the CVRP with OR-Tools — each route starts at the truck's
     current location, visits a subset of containers respecting capacity,
     and ends at the truck's depot.
  4. For each truck's solution, asks OSRM for the full polyline geometry
     of that ordered route.

This is the core of the operational scenario: it replaces the toy greedy
nearest-neighbor heuristic in services/optimizer.py with a real CVRP that
respects truck capacities and uses real driving distances.

Why CVRP and not CVRPTW? Time windows make the problem an order of
magnitude harder to solve and the marginal value for our hackathon demo
is small. We can layer time windows on top later.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.services import osrm_client

logger = logging.getLogger(__name__)


@dataclass
class TruckInput:
    id: str
    start_lat: float          # current location (where the solver picks up)
    start_lon: float
    end_lat: float            # depot (where the route returns)
    end_lon: float
    capacity_m3: float
    current_load_m3: float    # already on board, subtracted from capacity


@dataclass
class ContainerInput:
    container_id: str
    latitude: float
    longitude: float
    fill_level: float
    demand_m3: float = 1.0    # how much volume this container contributes


@dataclass
class TruckRouteSolution:
    truck_id: str
    stops: list[dict]                       # ordered list of stops with metadata
    polyline_geojson: dict                  # GeoJSON LineString
    distance_km: float
    duration_min: float


def _build_distance_matrix(
    trucks: Sequence[TruckInput],
    containers: Sequence[ContainerInput],
) -> tuple[list[list[int]], list[tuple[float, float]], dict]:
    """Build the OR-Tools-friendly distance matrix.

    Node layout:
      [0 .. N_trucks-1]                       -> truck start positions
      [N_trucks .. N_trucks+N_trucks-1]       -> truck depots (end nodes)
      [2*N_trucks .. 2*N_trucks+N_cont-1]     -> container nodes

    OR-Tools needs integer distances, so we round meters to int.
    """
    coords: list[tuple[float, float]] = []
    for t in trucks:
        coords.append((t.start_lat, t.start_lon))
    for t in trucks:
        coords.append((t.end_lat, t.end_lon))
    for c in containers:
        coords.append((c.latitude, c.longitude))

    table = osrm_client.get_table(coords)
    raw = table["distances"]
    if not raw:
        raise RuntimeError("OSRM returned an empty distance matrix")

    # OR-Tools wants integers; we use meters.
    matrix = [[int(round(d if d is not None else 9_999_999)) for d in row] for row in raw]

    layout = {
        "n_trucks": len(trucks),
        "truck_start": list(range(0, len(trucks))),
        "truck_end": list(range(len(trucks), 2 * len(trucks))),
        "containers": list(range(2 * len(trucks), 2 * len(trucks) + len(containers))),
    }
    return matrix, coords, layout


def solve(
    trucks: Sequence[TruckInput],
    containers: Sequence[ContainerInput],
    *,
    time_limit_seconds: int = 5,
) -> list[TruckRouteSolution]:
    """Run the CVRP solver and return one TruckRouteSolution per truck.

    A truck with no assigned stops is omitted from the result. The caller
    is responsible for marking those trucks as idle.
    """
    if not trucks or not containers:
        return []

    matrix, coords, layout = _build_distance_matrix(trucks, containers)
    n_trucks = layout["n_trucks"]
    container_nodes = layout["containers"]

    manager = pywrapcp.RoutingIndexManager(
        len(matrix),
        n_trucks,
        layout["truck_start"],
        layout["truck_end"],
    )
    routing = pywrapcp.RoutingModel(manager)

    # ----- distance callback -----
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # ----- capacity dimension -----
    # Demands are in milliliters of m3 to keep things integer (1 m3 = 1000)
    SCALE = 1000
    demands = [0] * len(matrix)
    for i, c in enumerate(containers):
        demands[container_nodes[i]] = int(round(c.demand_m3 * SCALE))

    def demand_callback(from_index):
        return demands[manager.IndexToNode(from_index)]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)

    capacities = [
        max(0, int(round((t.capacity_m3 - t.current_load_m3) * SCALE)))
        for t in trucks
    ]
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,            # no slack
        capacities,   # per-vehicle capacity (remaining headroom)
        True,         # start cumul to zero
        "Capacity",
    )

    # ----- allow dropping containers we can't fit -----
    # Without this, OR-Tools fails when total demand > total capacity.
    # Each dropped container costs more than any reasonable route distance,
    # so the solver only drops when truly necessary.
    DROP_PENALTY = 10_000_000
    for node in container_nodes:
        routing.AddDisjunction([manager.NodeToIndex(node)], DROP_PENALTY)

    # ----- search parameters -----
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(time_limit_seconds)

    solution = routing.SolveWithParameters(params)
    if solution is None:
        logger.warning("[vrp] CVRP solver returned no solution")
        return []

    # ----- decode solution -----
    results: list[TruckRouteSolution] = []
    for vehicle_idx, truck in enumerate(trucks):
        stops_nodes: list[int] = []
        index = routing.Start(vehicle_idx)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node in container_nodes:
                stops_nodes.append(node)
            index = solution.Value(routing.NextVar(index))

        if not stops_nodes:
            continue  # idle truck — skip

        # Map back to ContainerInput entries
        container_map = {container_nodes[i]: containers[i] for i in range(len(containers))}
        ordered_containers = [container_map[n] for n in stops_nodes]

        # Build the polyline by asking OSRM for the actual route
        # (truck_start -> stops[] -> depot)
        route_coords = (
            [(truck.start_lat, truck.start_lon)]
            + [(c.latitude, c.longitude) for c in ordered_containers]
            + [(truck.end_lat, truck.end_lon)]
        )
        try:
            route = osrm_client.get_route(route_coords)
        except osrm_client.OSRMError as exc:
            logger.warning("[vrp] OSRM /route failed for %s: %s", truck.id, exc)
            continue

        # Compute cumulative distance per stop (so the simulator can
        # interpolate position along the polyline correctly).
        cumulative_m = 0.0
        stops_payload: list[dict] = []
        for i, c in enumerate(ordered_containers):
            # Leg i is from waypoint i to waypoint i+1 — the i-th leg ends
            # at stop i (since stops start at index 1 in route_coords).
            cumulative_m += float(route["legs"][i]["distance"]) if i < len(route["legs"]) else 0.0
            stops_payload.append({
                "order": i + 1,
                "container_id": c.container_id,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "fill_level": c.fill_level,
                "status": "pending",
                "distance_along_route_m": round(cumulative_m, 2),
            })

        results.append(TruckRouteSolution(
            truck_id=truck.id,
            stops=stops_payload,
            polyline_geojson=route["geometry"],
            distance_km=round(route["distance_m"] / 1000.0, 3),
            duration_min=round(route["duration_s"] / 60.0, 2),
        ))

    return results
