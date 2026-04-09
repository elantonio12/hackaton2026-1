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

    model_config = {"from_attributes": True}

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


# ---------------------------------------------------------------------------
# Sensor CRUD
# ---------------------------------------------------------------------------

class SensorUpdate(BaseModel):
    """Actualizacion parcial de un sensor registrado."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zone: Optional[str] = None
    activo: Optional[bool] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class ZoneMetrics(BaseModel):
    zone: str
    total_containers: int
    critical_containers: int
    avg_fill_level: float
    avg_fill_rate_per_hour: float


class EfficiencyMetrics(BaseModel):
    optimized_distance_km: float
    standard_distance_km: float
    distance_saved_km: float
    distance_reduction_pct: float
    total_containers_visited: int
    vehicles_used: int


class EnvironmentalMetrics(BaseModel):
    fuel_saved_liters: float
    co2_avoided_kg: float
    diesel_price_mxn: float
    fuel_cost_saved_mxn: float


class FinancialMetrics(BaseModel):
    daily_fuel_savings_mxn: float
    monthly_fuel_savings_mxn: float
    yearly_fuel_savings_mxn: float
    cost_per_optimized_route_mxn: float
    cost_per_standard_route_mxn: float


class SystemStatus(BaseModel):
    total_containers_monitored: int
    total_sensors_registered: int
    total_collectors: int
    active_collectors: int
    containers_critical: int
    containers_predicted_full_24h: int
    prediction_model_trained: bool


class MetricsResponse(BaseModel):
    efficiency: EfficiencyMetrics
    environmental: EnvironmentalMetrics
    financial: FinancialMetrics
    system: SystemStatus
    zones: list[ZoneMetrics]
    generated_at: str
