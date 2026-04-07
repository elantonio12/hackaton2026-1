from pydantic import BaseModel


class ContainerReading(BaseModel):
    container_id: str
    latitude: float
    longitude: float
    fill_level: float  # 0.0 to 1.0
    zone: str
    timestamp: str


class RouteStop(BaseModel):
    container_id: str
    latitude: float
    longitude: float
    fill_level: float
    order: int


class OptimizedRoute(BaseModel):
    vehicle_id: str
    stops: list[RouteStop]
    total_distance_km: float
    estimated_time_min: float
    containers_visited: int


class CitizenReport(BaseModel):
    latitude: float
    longitude: float
    description: str
    zone: str
