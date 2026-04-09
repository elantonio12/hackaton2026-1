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

class SensorPayload(BaseModel):
    """What a physical sensor sends."""
    sensor_id: str
    fill_level: float  # 0.0 to 1.0
    height_cm: float   # height of trash measured by ultrasonic sensor


class SensorRegistration(BaseModel):
    """Register a sensor to a container location."""
    sensor_id: str
    container_id: str
    latitude: float
    longitude: float
    zone: str


class SensorInfo(SensorRegistration):
    pass


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


class ContainerPrediction(BaseModel):
    container_id: str
    zone: str
    current_fill_level: float
    predicted_fill_24h: float
    estimated_hours_to_full: float | None = None
    estimated_full_at: str | None = None
    fill_rate_per_hour: float
    confidence: str


class PredictionResponse(BaseModel):
    predictions: list[ContainerPrediction]
    model_trained: bool
    model_loss: float | None = None
    generated_at: str


class ModelStatus(BaseModel):
    is_trained: bool
    training_samples: int
    last_trained_at: str | None = None
    loss: float | None = None
    readings_since_last_train: int
    next_retrain_in: int
