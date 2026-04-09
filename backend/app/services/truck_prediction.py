"""
Truck Arrival Prediction Service - EcoRuta
==========================================
Predice la hora estimada de llegada (ETA) de un camión recolector
a un contenedor específico dentro de su ruta.

Modelo: MLPRegressor entrenado con historial sintético de rutas
Features:
  - Zona codificada (norte=0, centro=1, sur=2)
  - Orden de la parada en la ruta (1, 2, 3...)
  - Total de paradas en la ruta
  - Distancia acumulada hasta esa parada (km)
  - Hora de inicio de la ruta (sin/cos cíclico)
  - Día de la semana (sin/cos cíclico)
  - Nivel de llenado del contenedor (contenedores más llenos se priorizan)

Target: minutos desde el inicio de la ruta hasta llegar a esa parada
"""

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from sklearn.neural_network import MLPRegressor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ZONE_MAP = {"norte": 0, "centro": 1, "sur": 2}

# Velocidad promedio del camión en CDMX (km/h) — mismo valor que metrics.py
AVG_SPEED_KMH = 30.0

# Tiempo promedio de recolección por contenedor (minutos)
COLLECTION_TIME_MIN = 5.0

# Hora de inicio de ruta por zona (hora local CDMX)
ZONE_START_HOURS = {"norte": 7, "centro": 8, "sur": 9}

# Distancia promedio entre contenedores por zona (km) — basado en simulator coords
ZONE_AVG_DISTANCE_KM = {"norte": 0.8, "centro": 0.6, "sur": 1.0}

MIN_TRAINING_SAMPLES = 30


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RouteRecord:
    """Registro de una ruta histórica para entrenamiento."""
    zone: str
    container_id: str
    stop_order: int           # posición en la ruta (1-based)
    total_stops: int          # total de paradas en esa ruta
    distance_to_stop_km: float  # distancia acumulada desde el inicio hasta esta parada
    fill_level: float         # nivel de llenado del contenedor
    start_hour: float         # hora de inicio de la ruta (e.g. 7.5 = 7:30am)
    day_of_week: int          # 0=lunes ... 6=domingo
    actual_eta_minutes: float # minutos reales desde inicio hasta llegar


# Historial de rutas para entrenamiento
route_history: list[RouteRecord] = []


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _extract_features(record: RouteRecord) -> list[float]:
    """Extrae 9 features de un registro de ruta."""
    zone_encoded = ZONE_MAP.get(record.zone, 0)

    # Codificación cíclica de hora de inicio
    hour_sin = math.sin(2 * math.pi * record.start_hour / 24)
    hour_cos = math.cos(2 * math.pi * record.start_hour / 24)

    # Codificación cíclica del día de la semana
    dow_sin = math.sin(2 * math.pi * record.day_of_week / 7)
    dow_cos = math.cos(2 * math.pi * record.day_of_week / 7)

    # Ratio de posición en la ruta (0.0 a 1.0)
    stop_ratio = record.stop_order / max(record.total_stops, 1)

    return [
        zone_encoded,
        hour_sin,
        hour_cos,
        dow_sin,
        dow_cos,
        stop_ratio,
        record.distance_to_stop_km,
        record.fill_level,
        record.total_stops,
    ]


# ---------------------------------------------------------------------------
# MLP Model
# ---------------------------------------------------------------------------

class TruckArrivalPredictor:
    def __init__(self):
        self.model = MLPRegressor(
            hidden_layer_sizes=(64, 32, 16),
            activation="relu",
            solver="adam",
            max_iter=300,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
            warm_start=True,
        )
        self.is_trained: bool = False
        self.training_samples_count: int = 0
        self.last_trained_at: datetime | None = None
        self.loss: float | None = None
        self.retrain_threshold: int = 200
        self._records_since_last_train: int = 0

    def train(self, records: list[RouteRecord]) -> dict:
        if len(records) < MIN_TRAINING_SAMPLES:
            return {"error": "Not enough data", "samples": len(records)}

        X = [_extract_features(r) for r in records]
        y = [r.actual_eta_minutes for r in records]

        self.model.fit(X, y)
        self.is_trained = True
        self.training_samples_count = len(records)
        self.last_trained_at = datetime.now(timezone.utc)
        self.loss = float(self.model.loss_)
        self._records_since_last_train = 0

        logger.info(
            "[TruckPrediction] Trained on %d samples, loss=%.4f",
            len(records), self.loss,
        )

        return {
            "samples": len(records),
            "loss": self.loss,
            "n_iter": self.model.n_iter_,
        }

    def predict_eta_minutes(self, record: RouteRecord) -> float:
        """Predice minutos desde inicio de ruta hasta llegar al contenedor."""
        if not self.is_trained:
            # Fallback: estimación lineal simple si el modelo no está listo
            travel_min = (record.distance_to_stop_km / AVG_SPEED_KMH) * 60
            collection_min = (record.stop_order - 1) * COLLECTION_TIME_MIN
            return round(travel_min + collection_min, 1)

        features = [_extract_features(record)]
        result = self.model.predict(features)[0]
        return round(max(0.0, result), 1)

    def should_retrain(self) -> bool:
        return self._records_since_last_train >= self.retrain_threshold

    def record_new_data(self):
        self._records_since_last_train += 1


# Singleton
truck_predictor = TruckArrivalPredictor()


# ---------------------------------------------------------------------------
# Seed sintético — simula semanas de rutas históricas
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def generate_seed_routes(num_weeks: int = 4) -> None:
    """
    Genera historial sintético de rutas para entrenar el modelo.
    Simula num_weeks semanas de operación para las 3 zonas.
    """
    random.seed(42)

    # Días de recolección por zona (igual que ZONE_SCHEDULES en user.py)
    zone_collection_days = {
        "norte":  [0, 2, 4],   # lunes, miércoles, viernes
        "centro": [1, 3, 5],   # martes, jueves, sábado
        "sur":    [0, 3],      # lunes, jueves
    }

    # Centros de zona (del simulator/sensors/container.py)
    zone_centers = {
        "norte":  {"lat": 19.4890, "lon": -99.1250},
        "centro": {"lat": 19.4326, "lon": -99.1332},
        "sur":    {"lat": 19.3600, "lon": -99.1560},
    }

    containers_per_zone = {"norte": 17, "centro": 17, "sur": 16}

    now = datetime.now(timezone.utc)

    for week in range(num_weeks):
        for zone, collection_days in zone_collection_days.items():
            center = zone_centers[zone]
            n_containers = containers_per_zone[zone]
            start_hour = ZONE_START_HOURS[zone]

            for day_offset in collection_days:
                # Día real dentro de la semana
                days_back = (num_weeks - week) * 7 - day_offset
                route_date = now - timedelta(days=days_back)
                dow = route_date.weekday()

                # Número de paradas ese día (varía un poco)
                n_stops = random.randint(
                    max(5, n_containers - 5),
                    n_containers
                )

                # Generar contenedores de la ruta con coords aleatorias
                stops = []
                for i in range(n_stops):
                    stops.append({
                        "lat": center["lat"] + random.uniform(-0.02, 0.02),
                        "lon": center["lon"] + random.uniform(-0.02, 0.02),
                        "fill_level": random.uniform(0.5, 1.0),
                        "container_id": f"CNT-{zone[:1].upper()}{i+1:02d}",
                    })

                # Calcular distancias acumuladas entre paradas
                cumulative_km = 0.0
                elapsed_min = 0.0

                # Variación de tráfico: mañana más lento
                traffic_factor = random.uniform(0.8, 1.3)
                effective_speed = AVG_SPEED_KMH / traffic_factor

                prev_lat = center["lat"]
                prev_lon = center["lon"]

                for order, stop in enumerate(stops, start=1):
                    dist = _haversine(prev_lat, prev_lon, stop["lat"], stop["lon"])
                    cumulative_km += dist

                    # Tiempo de viaje + tiempo de recolección acumulado
                    travel_min = (dist / effective_speed) * 60
                    elapsed_min += travel_min + COLLECTION_TIME_MIN

                    # Pequeña variación aleatoria (semáforos, tráfico puntual)
                    elapsed_min += random.gauss(0, 1.5)
                    elapsed_min = max(0.0, elapsed_min)

                    record = RouteRecord(
                        zone=zone,
                        container_id=stop["container_id"],
                        stop_order=order,
                        total_stops=n_stops,
                        distance_to_stop_km=round(cumulative_km, 3),
                        fill_level=stop["fill_level"],
                        start_hour=start_hour + random.uniform(-0.25, 0.25),
                        day_of_week=dow,
                        actual_eta_minutes=round(elapsed_min, 2),
                    )
                    route_history.append(record)

                    prev_lat = stop["lat"]
                    prev_lon = stop["lon"]

    logger.info("[TruckPrediction] Generated %d synthetic route records", len(route_history))


def train_initial_model() -> dict:
    """Genera historial sintético y entrena el modelo inicial."""
    generate_seed_routes(num_weeks=4)
    metrics = truck_predictor.train(route_history)
    print(
        f"[TruckPrediction] Model trained on {metrics.get('samples', 0)} samples, "
        f"loss={metrics.get('loss', 'N/A')}"
    )
    return metrics


# ---------------------------------------------------------------------------
# Aprendizaje en línea — registrar rutas reales del optimizador
# ---------------------------------------------------------------------------

def register_optimized_route(optimized_routes: list) -> None:
    """
    Recibe las rutas generadas por el optimizador y las convierte en
    RouteRecords para reentrenar el modelo con datos reales.

    Llama esto desde routes.py después de generate_optimized_routes().
    """
    now = datetime.now(timezone.utc)
    dow = now.weekday()

    cdmx_now = now - timedelta(hours=6)
    start_hour = cdmx_now.hour + cdmx_now.minute / 60.0

    for route in optimized_routes:
        zone = _infer_zone_from_route(route)
        cumulative_km = 0.0
        elapsed_min = 0.0
        prev_lat = None
        prev_lon = None

        for stop in route.stops:
            if prev_lat is not None:
                dist = _haversine(prev_lat, prev_lon, stop.latitude, stop.longitude)
            else:
                dist = 0.0

            cumulative_km += dist
            travel_min = (dist / AVG_SPEED_KMH) * 60
            elapsed_min += travel_min + COLLECTION_TIME_MIN

            record = RouteRecord(
                zone=zone,
                container_id=stop.container_id,
                stop_order=stop.order,
                total_stops=len(route.stops),
                distance_to_stop_km=round(cumulative_km, 3),
                fill_level=stop.fill_level,
                start_hour=start_hour,
                day_of_week=dow,
                actual_eta_minutes=round(elapsed_min, 2),
            )
            route_history.append(record)
            truck_predictor.record_new_data()

            prev_lat = stop.latitude
            prev_lon = stop.longitude

    # Reentrenar si hay suficientes datos nuevos
    if truck_predictor.should_retrain():
        truck_predictor.train(route_history)


def _infer_zone_from_route(route) -> str:
    """Infiere la zona de una ruta mirando el primer stop."""
    if not route.stops:
        return "centro"
    stop = route.stops[0]
    lat = stop.latitude
    if lat >= 19.46:
        return "norte"
    elif lat <= 19.39:
        return "sur"
    return "centro"


# ---------------------------------------------------------------------------
# Predicción pública
# ---------------------------------------------------------------------------

def predict_truck_eta(
    container_id: str,
    zone: str,
    stop_order: int,
    total_stops: int,
    distance_to_stop_km: float,
    fill_level: float,
) -> dict:
    """
    Predice la ETA del camión a un contenedor específico.
    Retorna minutos desde inicio de ruta + hora estimada de llegada.
    """
    now = datetime.now(timezone.utc)
    cdmx_now = now - timedelta(hours=6)
    start_hour = ZONE_START_HOURS.get(zone, 8)
    dow = cdmx_now.weekday()

    record = RouteRecord(
        zone=zone,
        container_id=container_id,
        stop_order=stop_order,
        total_stops=total_stops,
        distance_to_stop_km=distance_to_stop_km,
        fill_level=fill_level,
        start_hour=float(start_hour),
        day_of_week=dow,
        actual_eta_minutes=0.0,  # target desconocido, se predice
    )

    eta_minutes = truck_predictor.predict_eta_minutes(record)

    # Hora de llegada = hora de inicio de ruta + eta_minutes
    route_start = cdmx_now.replace(
        hour=start_hour, minute=0, second=0, microsecond=0
    )
    arrival_time = route_start + timedelta(minutes=eta_minutes)

    return {
        "container_id": container_id,
        "zone": zone,
        "stop_order": stop_order,
        "total_stops": total_stops,
        "eta_minutes_from_route_start": eta_minutes,
        "estimated_arrival_time": arrival_time.strftime("%H:%M"),
        "estimated_arrival_datetime": (arrival_time + timedelta(hours=6)).isoformat(),  # UTC
        "model_trained": truck_predictor.is_trained,
        "confidence": "high" if truck_predictor.is_trained else "low (fallback lineal)",
    }
