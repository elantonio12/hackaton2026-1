"""Prediction service: Granite TTM R2 zero-shot fill-level forecasting."""

import logging
import math
import random
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import torch
from tsfm_public.toolkit.get_model import get_model

from app.core.config import settings
from app.models.schemas import ContainerReading
from app.services import watsonx_forecast

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

ZONE_MAP = {"centro": 0, "norte": 1, "sur": 2}

# Fill rates per hour by zone (base, before time-of-day modulation)
ZONE_FILL_RATES = {"centro": 0.035, "norte": 0.025, "sur": 0.020}

MIN_TRAINING_SAMPLES = 50

# TTM R2 configuration
RESAMPLE_INTERVAL = timedelta(minutes=15)
CONTEXT_LENGTH = 512       # 512 * 15min = 5.3 days of history
PREDICTION_LENGTH = 96     # 96 * 15min = 24 hours of forecast
MIN_CONTEXT_POINTS = 96    # Minimum resampled points to attempt TTM prediction


@dataclass
class HistoricalReading:
    container_id: str
    fill_level: float
    zone: str
    timestamp: datetime


# Main history store: container_id -> deque of readings
container_history: dict[str, deque[HistoricalReading]] = {}

# ---------------------------------------------------------------------------
# Resampling utilities (replaces manual feature engineering)
# ---------------------------------------------------------------------------


def _resample_to_15min(
    history: deque[HistoricalReading] | list[HistoricalReading],
) -> list[float]:
    """Resample irregular fill_level readings to regular 15-minute intervals.

    Uses last-observation-carried-forward (LOCF) interpolation.
    """
    if len(history) < 2:
        return []

    readings = list(history)
    timestamps = [r.timestamp for r in readings]
    first_ts = timestamps[0]
    last_ts = timestamps[-1]

    # Build regular 15-minute grid
    grid: list[float] = []
    t = first_ts
    while t <= last_ts:
        # Find the closest reading at-or-before t via binary search
        idx = bisect_left(timestamps, t)
        if idx >= len(timestamps):
            idx = len(timestamps) - 1
        elif idx > 0 and timestamps[idx] > t:
            idx -= 1
        grid.append(readings[idx].fill_level)
        t += RESAMPLE_INTERVAL

    return grid


def _pad_or_truncate(series: list[float], target_length: int) -> list[float]:
    """Pad front with first value or truncate to most recent target_length points."""
    if len(series) >= target_length:
        return series[-target_length:]
    pad_count = target_length - len(series)
    return [series[0]] * pad_count + series


# ---------------------------------------------------------------------------
# Legacy feature engineering (kept for backward compatibility)
# ---------------------------------------------------------------------------


def _extract_features(
    reading: HistoricalReading,
    history: deque[HistoricalReading] | list[HistoricalReading],
) -> list[float]:
    """Extract 7 features from a reading + its history context."""
    ts = reading.timestamp

    hour = ts.hour + ts.minute / 60.0
    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)

    dow = ts.weekday()
    dow_sin = math.sin(2 * math.pi * dow / 7)
    dow_cos = math.cos(2 * math.pi * dow / 7)

    zone_encoded = ZONE_MAP.get(reading.zone, 0)
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
    history: deque[HistoricalReading] | list[HistoricalReading],
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
        past = history[0]

    dt_seconds = (current.timestamp - past.timestamp).total_seconds()
    if dt_seconds < 1.0:
        return 0.0

    return (current.fill_level - past.fill_level) / (dt_seconds / 3600)


# ---------------------------------------------------------------------------
# Training data construction (kept for backward compatibility)
# ---------------------------------------------------------------------------

DOWNSAMPLE_INTERVAL = timedelta(minutes=10)


def _build_training_set(
    history: dict[str, deque[HistoricalReading]],
) -> tuple[list[list[float]], list[float]]:
    """Build (X, y) pairs. Kept for /retrain endpoint compatibility."""
    X: list[list[float]] = []
    y: list[float] = []

    for container_id, readings in history.items():
        readings_list = list(readings)
        n = len(readings_list)
        if n < 10:
            continue

        timestamps = [r.timestamp for r in readings_list]
        last_sampled: datetime | None = None

        for i in range(n):
            r = readings_list[i]
            if last_sampled is not None and (r.timestamp - last_sampled) < DOWNSAMPLE_INTERVAL:
                continue
            last_sampled = r.timestamp

            target_time = r.timestamp + timedelta(hours=24)
            j = bisect_left(timestamps, target_time)

            best = None
            best_diff = timedelta(hours=2)
            for candidate in (j - 1, j):
                if 0 <= candidate < n and candidate != i:
                    diff = abs(timestamps[candidate] - target_time)
                    if diff < best_diff:
                        best_diff = diff
                        best = candidate

            if best is not None:
                context_start = max(0, i - 200)
                context = readings_list[context_start:i + 1]
                features = _extract_features(r, context)
                X.append(features)
                y.append(readings_list[best].fill_level)

    return X, y


# ---------------------------------------------------------------------------
# Granite TTM R2 predictor
# ---------------------------------------------------------------------------


class FillLevelPredictor:
    def __init__(self):
        self.model = None
        self.is_trained: bool = False
        self.training_samples_count: int = 0
        self.last_trained_at: datetime | None = None
        self.loss: float | None = None
        self.retrain_threshold: int = 500
        self._readings_since_last_train: int = 0

    def load_model(self) -> None:
        """Load the pre-trained Granite TTM R2 model (zero-shot)."""
        self.model = get_model(
            model_path="ibm-granite/granite-timeseries-ttm-r2",
            context_length=CONTEXT_LENGTH,
            prediction_length=PREDICTION_LENGTH,
        )
        self.model.eval()
        self.is_trained = True
        logger.info("[Prediction] Granite TTM R2 loaded (zero-shot, ctx=%d, pred=%d)",
                     CONTEXT_LENGTH, PREDICTION_LENGTH)

    def train(self, X: list[list[float]], y: list[float]) -> dict:
        """Backward-compatible train method. TTM is zero-shot, so this updates metadata only."""
        if len(X) < MIN_TRAINING_SAMPLES:
            return {"error": "Not enough data", "samples": len(X)}

        self.is_trained = True
        self.training_samples_count = len(X)
        self.last_trained_at = datetime.now(timezone.utc)
        self.loss = None
        self._readings_since_last_train = 0

        logger.info(
            "[Prediction] TTM R2 ready (zero-shot), %d history samples available",
            len(X),
        )
        return {"samples": len(X), "loss": None, "n_iter": 0}

    def predict_fill_trajectory(
        self, history: deque[HistoricalReading] | list[HistoricalReading],
    ) -> np.ndarray | None:
        """Predict fill levels for the next 24 hours.

        Primary: local Granite TTM R2 (zero-shot, CPU).
        Fallback: IBM watsonx.ai hosted Granite TTM API.

        Returns array of 96 predicted values (15-min intervals) or None.
        """
        series = _resample_to_15min(history)
        if len(series) < MIN_CONTEXT_POINTS:
            return None

        # Path 1: local TTM R2 (skipped if forcing watsonx)
        if not settings.force_watsonx_forecast and self.model is not None:
            try:
                series_padded = _pad_or_truncate(series, CONTEXT_LENGTH)
                input_tensor = torch.tensor(
                    series_padded, dtype=torch.float32,
                ).unsqueeze(0).unsqueeze(-1)
                with torch.no_grad():
                    output = self.model(input_tensor)
                predictions = output.prediction_outputs[0, :, 0].numpy()
                return np.clip(predictions, 0.0, 1.0)
            except Exception as e:
                logger.warning("[Prediction] Local TTM inference failed: %s", e)

        # Path 2: watsonx.ai fallback
        if watsonx_forecast.is_available():
            readings = list(history)
            last_ts = readings[-1].timestamp
            first_ts = last_ts - RESAMPLE_INTERVAL * (len(series) - 1)
            timestamps = [
                (first_ts + RESAMPLE_INTERVAL * i).isoformat()
                for i in range(len(series))
            ]
            watsonx_preds = watsonx_forecast.forecast_fill_trajectory(
                timestamps=timestamps,
                fill_levels=series,
                prediction_length=PREDICTION_LENGTH,
            )
            if watsonx_preds:
                return np.array(watsonx_preds, dtype=np.float32)

        return None

    def predict(self, features: list[list[float]]) -> list[float]:
        """Legacy predict method. Kept for API compatibility."""
        if not self.is_trained:
            raise ValueError("Model not trained yet")
        return [0.5] * len(features)

    def should_retrain(self) -> bool:
        return self._readings_since_last_train >= self.retrain_threshold

    def record_new_reading(self):
        self._readings_since_last_train += 1


# Module-level singleton
predictor = FillLevelPredictor()

# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

MAX_HISTORY_PER_CONTAINER = 52000  # ~6 days at 10s intervals


def _ensure_utc(ts: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def append_reading(reading: ContainerReading) -> None:
    """Append a ContainerReading to the history buffer."""
    cid = reading.container_id
    if cid not in container_history:
        container_history[cid] = deque(maxlen=MAX_HISTORY_PER_CONTAINER)

    try:
        ts = _ensure_utc(datetime.fromisoformat(reading.timestamp))
    except (ValueError, TypeError):
        logger.warning("Malformed timestamp for %s: %r, using now()", cid, reading.timestamp)
        ts = datetime.now(timezone.utc)

    container_history[cid].append(
        HistoricalReading(
            container_id=cid,
            fill_level=max(0.0, min(1.0, reading.fill_level)),
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
    if len(X) < MIN_TRAINING_SAMPLES:
        return None
    return predictor.train(X, y)


# ---------------------------------------------------------------------------
# Seed historical data (144h synthetic — 6 days for TTM context)
# ---------------------------------------------------------------------------


def generate_seed_history(sensors_list: list[dict]) -> None:
    """Generate 144h of synthetic history for all registered sensors."""
    random.seed(42)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=144)
    interval = timedelta(minutes=10)

    for info in sensors_list:
        cid = info["container_id"]
        zone = info["zone"]
        container_history[cid] = deque(maxlen=MAX_HISTORY_PER_CONTAINER)

        fill = random.uniform(0.05, 0.30)
        base_rate = ZONE_FILL_RATES.get(zone, 0.025)

        t = start
        while t <= now:
            hour = t.hour
            if 6 <= hour < 22:
                rate_mult = 1.3
            else:
                rate_mult = 0.5

            fill += base_rate * rate_mult * (10.0 / 60.0)
            fill += random.gauss(0, 0.02)
            fill = max(0.0, min(1.0, fill))

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
    """Load TTM R2 model and validate history is sufficient."""
    predictor.load_model()
    X, y = _build_training_set(container_history)
    metrics = predictor.train(X, y)
    print(f"[Prediction] Granite TTM R2 loaded, {metrics.get('samples', 0)} history samples available")
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

    fill_rate = _compute_fill_rate(latest, history)

    # Try TTM R2 prediction
    trajectory = predictor.predict_fill_trajectory(history)
    if trajectory is not None:
        predicted_24h = float(trajectory[-1])
    else:
        # Fallback to linear extrapolation
        predicted_24h = max(0.0, min(1.0, latest.fill_level + fill_rate * 24))

    # Estimate hours to full
    estimated_hours = None
    estimated_full_at = None

    if trajectory is not None:
        # Use trajectory to find when fill crosses threshold
        for i, val in enumerate(trajectory):
            if val >= threshold:
                estimated_hours = round((i + 1) * 0.25, 1)  # each step = 15min = 0.25h
                estimated_full_at = (
                    datetime.now(timezone.utc) + timedelta(hours=estimated_hours)
                ).isoformat()
                break
    elif fill_rate > 0.001 and latest.fill_level < threshold:
        estimated_hours = round((threshold - latest.fill_level) / fill_rate, 1)
        if estimated_hours > 720:
            estimated_hours = None
        else:
            estimated_full_at = (
                datetime.now(timezone.utc) + timedelta(hours=estimated_hours)
            ).isoformat()

    # Confidence based on model+linear agreement
    if fill_rate > 0.001 and estimated_hours is not None:
        model_says_full = predicted_24h >= threshold
        linear_says_full = (
            fill_rate > 0 and
            (threshold - latest.fill_level) / fill_rate <= 24
        ) if fill_rate > 0.001 else False
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

    results.sort(key=lambda p: p["estimated_hours_to_full"] or float("inf"))
    return results
