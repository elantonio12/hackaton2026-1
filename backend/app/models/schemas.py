from pydantic import BaseModel
from datetime import datetime 
from typing import Optional


class collectorBase(BaseModel):
    nombre: str
    empleado_id: str
    zona: str
    camion_id: str
    activo: bool = True
    telefono: Optional[str] = None

class CollectorCreate(collectorBase):
    pass

class CollectorUpdate(BaseModel):
    nombre: Optional[str] = None
    empleado_id: Optional[str] = None   
    zona: Optional[str] = None
    camion_id: Optional[str] = None
    activo: Optional[bool] = None
    telefono: Optional[str] = None  

class Collector(collectorBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class config:
        from_attributes = True

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
