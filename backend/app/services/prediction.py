"""Prediction service: historical buffer, MLP model, and fill-level forecasting."""

import math
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sklearn.neural_network import MLPRegressor

from app.models.schemas import ContainerReading

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

ZONE_MAP = {"centro": 0, "norte": 1, "sur": 2}

# Fill rates per hour by zone (base, before time-of-day modulation)
ZONE_FILL_RATES = {"centro": 0.035, "norte": 0.025, "sur": 0.020}


@dataclass
class HistoricalReading:
    container_id: str
    fill_level: float
    zone: str
    timestamp: datetime


# Main history store: container_id -> deque of readings
container_history: dict[str, deque[HistoricalReading]] = {}

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


def _extract_features(
    reading: HistoricalReading,
    history: deque[HistoricalReading],
) -> list[float]:
    """Extract 7 features from a reading + its history context."""
    ts = reading.timestamp

    # Cyclical time encoding
    hour = ts.hour + ts.minute / 60.0
    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)

    dow = ts.weekday()
    dow_sin = math.sin(2 * math.pi * dow / 7)
    dow_cos = math.cos(2 * math.pi * dow / 7)

    # Zone
    zone_encoded = ZONE_MAP.get(reading.zone, 0)

    # Fill rate: look back ~30 min
    fill_rate = _compute_fill_rate(reading, history)

    return [
        hour_sin,
        hour_cos,
        dow_sin,
        dow_cos,
        zone_encoded,
        fill_rate,
        reading.fill_level,
    ]


def _compute_fill_rate(
    current: HistoricalReading,
    history: deque[HistoricalReading],
    lookback_minutes: int = 30,
) -> float:
    """Compute fill change per hour using recent history."""
    if len(history) < 2:
        return 0.0

    cutoff = current.timestamp - timedelta(minutes=lookback_minutes)
    past = None
    for r in history:
        if r.timestamp <= cutoff:
            past = r
        elif past is not None:
            break

    if past is None:
        # Use oldest available
        past = history[0]

    dt_hours = (current.timestamp - past.timestamp).total_seconds() / 3600
    if dt_hours < 0.001:
        return 0.0

    return (current.fill_level - past.fill_level) / dt_hours


# ---------------------------------------------------------------------------
# Training data construction
# ---------------------------------------------------------------------------

DOWNSAMPLE_STEP = 60  # use every 60th reading for training (~10 min intervals)


def _build_training_set(
    history: dict[str, deque[HistoricalReading]],
) -> tuple[list[list[float]], list[float]]:
    """Build (X, y) pairs by matching readings 24h apart."""
    X: list[list[float]] = []
    y: list[float] = []

    for container_id, readings in history.items():
        readings_list = list(readings)
        n = len(readings_list)
        if n < 10:
            continue

        for i in range(0, n, DOWNSAMPLE_STEP):
            r = readings_list[i]
            target_time = r.timestamp + timedelta(hours=24)

            # Find closest reading to target_time
            best = None
            best_diff = timedelta(hours=2)  # max tolerance: 2h
            for j in range(i + 1, n):
                diff = abs(readings_list[j].timestamp - target_time)
                if diff < best_diff:
                    best_diff = diff
                    best = readings_list[j]
                elif readings_list[j].timestamp > target_time + timedelta(hours=2):
                    break

            if best is not None:
                features = _extract_features(r, deque(readings_list[max(0, i - 200):i + 1]))
                X.append(features)
                y.append(best.fill_level)

    return X, y


# ---------------------------------------------------------------------------
# MLP model
# ---------------------------------------------------------------------------


class FillLevelPredictor:
    def __init__(self):
        self.model: MLPRegressor | None = None
        self.is_trained: bool = False
        self.training_samples_count: int = 0
        self.last_trained_at: datetime | None = None
        self.loss: float | None = None
        self.retrain_threshold: int = 500
        self._readings_since_last_train: int = 0

    def train(self, X: list[list[float]], y: list[float]) -> dict:
        """Train or retrain the model. Returns metrics."""
        if len(X) < 10:
            return {"error": "Not enough data", "samples": len(X)}

        self.model = MLPRegressor(
            hidden_layer_sizes=(32, 16),
            activation="relu",
            solver="adam",
            max_iter=200,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
            warm_start=self.is_trained,
        )

        self.model.fit(X, y)
        self.is_trained = True
        self.training_samples_count = len(X)
        self.last_trained_at = datetime.now(timezone.utc)
        self.loss = float(self.model.loss_)
        self._readings_since_last_train = 0

        return {
            "samples": len(X),
            "loss": self.loss,
            "n_iter": self.model.n_iter_,
        }

    def predict(self, features: list[list[float]]) -> list[float]:
        if not self.is_trained or self.model is None:
            raise ValueError("Model not trained yet")
        return self.model.predict(features).tolist()

    def should_retrain(self) -> bool:
        return self._readings_since_last_train >= self.retrain_threshold

    def record_new_reading(self):
        self._readings_since_last_train += 1


# Module-level singleton
predictor = FillLevelPredictor()

# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

MAX_HISTORY_PER_CONTAINER = 26000  # ~72h at 10s intervals


def append_reading(reading: ContainerReading) -> None:
    """Append a ContainerReading to the history buffer."""
    cid = reading.container_id
    if cid not in container_history:
        container_history[cid] = deque(maxlen=MAX_HISTORY_PER_CONTAINER)

    try:
        ts = datetime.fromisoformat(reading.timestamp)
    except (ValueError, TypeError):
        ts = datetime.now(timezone.utc)

    container_history[cid].append(
        HistoricalReading(
            container_id=cid,
            fill_level=reading.fill_level,
            zone=reading.zone,
            timestamp=ts,
        )
    )
    predictor.record_new_reading()


def maybe_retrain() -> dict | None:
    """Retrain if enough new readings have accumulated."""
    if not predictor.should_retrain():
        return None
    X, y = _build_training_set(container_history)
    if len(X) < 100:
        return None
    return predictor.train(X, y)


# ---------------------------------------------------------------------------
# Seed historical data (72h synthetic)
# ---------------------------------------------------------------------------


def generate_seed_history(sensor_registry: dict[str, dict]) -> None:
    """Generate 72h of synthetic history for all registered sensors."""
    random.seed(42)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=72)
    interval = timedelta(minutes=10)

    for info in sensor_registry.values():
        cid = info["container_id"]
        zone = info["zone"]
        container_history[cid] = deque(maxlen=MAX_HISTORY_PER_CONTAINER)

        fill = random.uniform(0.05, 0.30)
        base_rate = ZONE_FILL_RATES.get(zone, 0.025)

        t = start
        while t <= now:
            # Time-of-day modulation
            hour = t.hour
            if 6 <= hour < 22:
                rate_mult = 1.3
            else:
                rate_mult = 0.5

            # Advance fill level (10-min step)
            fill += base_rate * rate_mult * (10.0 / 60.0)
            fill += random.gauss(0, 0.02)
            fill = max(0.0, min(1.0, fill))

            # Collection event
            if fill >= random.uniform(0.85, 0.95):
                fill = random.uniform(0.05, 0.15)

            container_history[cid].append(
                HistoricalReading(
                    container_id=cid,
                    fill_level=round(fill, 4),
                    zone=zone,
                    timestamp=t,
                )
            )
            t += interval


def train_initial_model() -> dict:
    """Build training set from seed history and train the model."""
    X, y = _build_training_set(container_history)
    metrics = predictor.train(X, y)
    print(f"[Prediction] Model trained on {metrics.get('samples', 0)} samples, "
          f"loss={metrics.get('loss', 'N/A')}")
    return metrics


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------


def predict_container(container_id: str, threshold: float = 0.8) -> dict | None:
    """Generate prediction for a single container."""
    history = container_history.get(container_id)
    if not history or len(history) < 2:
        return None

    latest = history[-1]

    if not predictor.is_trained:
        return None

    features = _extract_features(latest, history)
    predicted_24h = predictor.predict([features])[0]
    predicted_24h = max(0.0, min(1.0, predicted_24h))

    fill_rate = _compute_fill_rate(latest, history)

    # Estimate hours to full
    estimated_hours = None
    estimated_full_at = None
    if fill_rate > 0.001 and latest.fill_level < threshold:
        estimated_hours = round((threshold - latest.fill_level) / fill_rate, 1)
        estimated_full_at = (
            datetime.now(timezone.utc) + timedelta(hours=estimated_hours)
        ).isoformat()

    # Confidence
    if fill_rate > 0.001 and estimated_hours is not None:
        model_says_full = predicted_24h >= threshold
        linear_says_full = estimated_hours <= 24
        if model_says_full == linear_says_full:
            confidence = "high"
        else:
            confidence = "medium"
    else:
        confidence = "low"

    return {
        "container_id": container_id,
        "zone": latest.zone,
        "current_fill_level": round(latest.fill_level, 4),
        "predicted_fill_24h": round(predicted_24h, 4),
        "estimated_hours_to_full": estimated_hours,
        "estimated_full_at": estimated_full_at,
        "fill_rate_per_hour": round(fill_rate, 5),
        "confidence": confidence,
    }


def predict_all(zone: str | None = None, threshold: float = 0.8) -> list[dict]:
    """Get predictions for all containers, optionally filtered by zone."""
    results = []
    for cid in container_history:
        pred = predict_container(cid, threshold)
        if pred is None:
            continue
        if zone and pred["zone"] != zone:
            continue
        results.append(pred)

    # Sort by urgency: containers closest to full first
    results.sort(key=lambda p: p["estimated_hours_to_full"] or float("inf"))
    return results
