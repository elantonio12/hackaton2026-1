"""Prediction service: client-side state for fill-level forecasting.

The actual TTM model lives in the ml-service container — we used to
load it in-process here but every uvicorn worker would load its own
copy of the ~300 MB model. Extracting it lets backend run with more
workers and a much smaller image.

What's still owned by backend:
  - `container_history`: in-memory deques of recent readings, fed by
    the sensor ingest hot path. Resampled to a 15-min grid before
    being sent to ml-service.
  - `append_reading`, `generate_seed_history`: history bookkeeping.
  - `predict_all`, `predict_container`: thin orchestrators that
    resample, POST to ml-service, and decorate the result.
  - The `predictor` shim: a minimal singleton holding metadata so
    the legacy /predictions/model-status endpoint still works.

What moved to ml-service:
  - torch, tsfm_public, the actual TTM model
  - watsonx.ai fallback
"""

import logging
import math
import random
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from app.models.schemas import ContainerReading
from app.services import ml_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

ZONE_MAP = {"centro": 0, "norte": 1, "sur": 2}

# Fill rates per hour by zone (base, before time-of-day modulation)
ZONE_FILL_RATES = {"centro": 0.035, "norte": 0.025, "sur": 0.020}

MIN_TRAINING_SAMPLES = 50

# TTM R2 contract — must match ml-service/app/predictor.py
RESAMPLE_INTERVAL = timedelta(minutes=15)
CONTEXT_LENGTH = ml_client.CONTEXT_LENGTH         # 512
PREDICTION_LENGTH = ml_client.PREDICTION_LENGTH   # 96
MIN_CONTEXT_POINTS = 96    # need at least 24h of resampled history to bother


@dataclass
class HistoricalReading:
    container_id: str
    fill_level: float
    zone: str
    timestamp: datetime


# Main history store: container_id -> deque of readings
container_history: dict[str, deque[HistoricalReading]] = {}

# ---------------------------------------------------------------------------
# Resampling utilities (run locally before posting to ml-service)
# ---------------------------------------------------------------------------


def _resample_to_15min(
    history: deque[HistoricalReading] | list[HistoricalReading],
) -> list[float]:
    """Resample irregular fill_level readings to a regular 15-minute grid.

    Last-observation-carried-forward (LOCF) interpolation. Returns the
    resampled fill_level series in chronological order.
    """
    if len(history) < 2:
        return []

    readings = list(history)
    timestamps = [r.timestamp for r in readings]
    first_ts = timestamps[0]
    last_ts = timestamps[-1]

    grid: list[float] = []
    t = first_ts
    while t <= last_ts:
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


def _build_training_set(
    history: dict[str, deque[HistoricalReading]],
) -> tuple[list[list[float]], list[float]]:
    """Counter for the legacy /predictions/retrain endpoint.

    TTM is zero-shot — there's nothing to actually train on the backend
    side anymore. We keep this so the endpoint can still report a
    sample count without crashing.
    """
    # Count how many history points we have, for the metadata response
    total = sum(len(h) for h in history.values())
    return [[]] * total, [0.0] * total


# ---------------------------------------------------------------------------
# Predictor shim — metadata only
# ---------------------------------------------------------------------------


class FillLevelPredictorShim:
    """Compatibility shim for code that used to talk to the in-process
    TTM model.

    `is_trained` is now derived from ml-service health (cached). The
    other fields are bookkeeping for the legacy /model-status endpoint.
    """

    def __init__(self) -> None:
        self.training_samples_count: int = 0
        self.last_trained_at: datetime | None = None
        self.loss: float | None = None
        self.retrain_threshold: int = 500
        self._readings_since_last_train: int = 0
        self._last_known_ready: bool = False

    @property
    def is_trained(self) -> bool:
        """Best-effort flag based on the last cached ml-service health probe.

        We can't make this property async, so we return the most recently
        observed value. Code paths that need a guaranteed-fresh value
        should `await ml_client.is_ready()` directly.
        """
        return self._last_known_ready

    async def refresh_ready(self) -> bool:
        self._last_known_ready = await ml_client.is_ready()
        return self._last_known_ready

    def record_new_reading(self) -> None:
        self._readings_since_last_train += 1

    def should_retrain(self) -> bool:
        return self._readings_since_last_train >= self.retrain_threshold

    def train(self, X: list[list[float]], y: list[float]) -> dict:
        """No-op compat shim — TTM is zero-shot, we just refresh metadata."""
        self.training_samples_count = len(X)
        self.last_trained_at = datetime.now(timezone.utc)
        self._readings_since_last_train = 0
        return {"samples": len(X), "loss": None, "n_iter": 0}


# Module-level singleton
predictor = FillLevelPredictorShim()


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

MAX_HISTORY_PER_CONTAINER = 1024  # 10.6 days at 15-min resample granularity

# Threshold above which we switch to a lightweight seed
LARGE_DEPLOYMENT_THRESHOLD = 500


def _ensure_utc(ts: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def append_reading(reading: ContainerReading) -> None:
    """Append a ContainerReading to the in-memory history buffer."""
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
    """No-op (TTM is zero-shot). Kept so the ingest path doesn't break."""
    return None


# ---------------------------------------------------------------------------
# Seed historical data
# ---------------------------------------------------------------------------


def generate_seed_history(sensors_list: list[dict]) -> None:
    """Generate synthetic seed history for all registered sensors.

    Switches to a lighter seed for large deployments (>500 sensors) to keep
    memory bounded while still providing enough context for TTM inference.
    """
    random.seed(42)
    now = datetime.now(timezone.utc)

    n = len(sensors_list)
    if n > LARGE_DEPLOYMENT_THRESHOLD:
        start = now - timedelta(hours=24)
        interval = timedelta(minutes=30)
        logger.info(
            "[Prediction] Large deployment (%d sensors): generating lightweight seed (24h @ 30min)",
            n,
        )
    else:
        start = now - timedelta(hours=144)
        interval = timedelta(minutes=10)
        logger.info(
            "[Prediction] Small deployment (%d sensors): generating rich seed (144h @ 10min)",
            n,
        )

    step_hours = interval.total_seconds() / 3600.0

    for info in sensors_list:
        cid = info["container_id"]
        zone = info["zone"]
        container_history[cid] = deque(maxlen=MAX_HISTORY_PER_CONTAINER)

        fill = random.uniform(0.05, 0.30)
        base_rate = ZONE_FILL_RATES.get(zone, 0.025)

        t = start
        while t <= now:
            hour = t.hour
            rate_mult = 1.3 if 6 <= hour < 22 else 0.5
            fill += base_rate * rate_mult * step_hours
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
    """Compatibility shim. The model lives in ml-service now — there's
    nothing to load locally. We just refresh the metadata so the legacy
    /predictions/model-status endpoint reports something sensible."""
    total_history = sum(len(h) for h in container_history.values())
    metrics = predictor.train([[]] * total_history, [0.0] * total_history)
    print(f"[Prediction] ml-service handles inference, {total_history} history samples seeded")
    return metrics


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------


def _build_prediction_dict(
    container_id: str,
    history: deque[HistoricalReading] | list[HistoricalReading],
    trajectory: np.ndarray | None,
    threshold: float,
) -> dict:
    """Build the public prediction dict from a container's history + trajectory."""
    latest = history[-1]
    fill_rate = _compute_fill_rate(latest, history)

    if trajectory is not None:
        predicted_24h = float(trajectory[-1])
    else:
        predicted_24h = max(0.0, min(1.0, latest.fill_level + fill_rate * 24))

    estimated_hours = None
    estimated_full_at = None

    if trajectory is not None:
        for i, val in enumerate(trajectory):
            if val >= threshold:
                estimated_hours = round((i + 1) * 0.25, 1)  # each step = 15min
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

    if fill_rate > 0.001 and estimated_hours is not None:
        model_says_full = predicted_24h >= threshold
        linear_says_full = (threshold - latest.fill_level) / fill_rate <= 24
        confidence = "high" if model_says_full == linear_says_full else "medium"
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


def _eligible_history(
    history: deque[HistoricalReading] | list[HistoricalReading],
) -> list[float] | None:
    """Resample + pad a single history. Returns None if too short."""
    series = _resample_to_15min(history)
    if len(series) < MIN_CONTEXT_POINTS:
        return None
    return _pad_or_truncate(series, CONTEXT_LENGTH)


async def predict_container(container_id: str, threshold: float = 0.8) -> dict | None:
    """Generate a prediction for a single container by container_id.

    Resamples that container's history locally, sends a 1-element batch
    to ml-service, decorates the result. Returns None if we don't have
    enough history or ml-service is down.
    """
    history = container_history.get(container_id)
    if not history or len(history) < 2:
        return None

    series = _eligible_history(history)
    trajectory: np.ndarray | None = None
    if series is not None:
        results = await ml_client.predict_batch([series])
        if results and results[0] is not None:
            trajectory = np.clip(np.array(results[0], dtype=np.float32), 0.0, 1.0)

    return _build_prediction_dict(container_id, history, trajectory, threshold)


async def predict_all(zone: str | None = None, threshold: float = 0.8) -> list[dict]:
    """Run predictions for every container with enough history.

    Optionally filtered by zone. Builds a single batch request to
    ml-service so the network round-trip cost is amortized.
    """
    # Collect eligible containers (optionally zone-filtered)
    eligible: list[tuple[str, deque[HistoricalReading], list[float]]] = []
    short: list[tuple[str, deque[HistoricalReading]]] = []

    for cid, history in container_history.items():
        if not history or len(history) < 2:
            continue
        if zone and history[-1].zone != zone:
            continue
        series = _eligible_history(history)
        if series is None:
            short.append((cid, history))
        else:
            eligible.append((cid, history, series))

    if not eligible and not short:
        return []

    # Single batch round-trip for everyone with sufficient history
    trajectories: list[np.ndarray | None] = []
    if eligible:
        series_payload = [s for _, _, s in eligible]
        responses = await ml_client.predict_batch(series_payload)
        for resp in responses:
            if resp is None:
                trajectories.append(None)
            else:
                trajectories.append(np.clip(np.array(resp, dtype=np.float32), 0.0, 1.0))

    results: list[dict] = []
    for (cid, hist, _), traj in zip(eligible, trajectories):
        results.append(_build_prediction_dict(cid, hist, traj, threshold))

    # Containers with insufficient history still get a linear-extrapolation
    # prediction so the dashboard isn't blank for fresh sensors.
    for cid, hist in short:
        results.append(_build_prediction_dict(cid, hist, None, threshold))

    results.sort(key=lambda p: p["estimated_hours_to_full"] or float("inf"))
    return results
