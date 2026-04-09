"""HTTP client for the ml-service container.

The backend used to load Granite TTM in-process; we extracted that to
its own container so the backend image stays lean and the model runs
in a single shared process instead of being duplicated across uvicorn
workers.

Communication contract:
  POST /predict_batch
    body  = {"series": [[float, ...], ...]}
    reply = {"predictions": [[float, ...] | null, ...], "elapsed_ms": float}

The caller is responsible for resampling raw readings to a regular
15-min grid and padding to CONTEXT_LENGTH before sending. ml-service
is intentionally stateless.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml-service:8001")
ML_REQUEST_TIMEOUT = float(os.environ.get("ML_SERVICE_TIMEOUT", "60"))

# Mirror of ml-service/app/predictor.py constants. Keep these in sync.
CONTEXT_LENGTH = 512
PREDICTION_LENGTH = 96

# Cached health probe — avoid spamming /health on every predict call.
_HEALTH_TTL_SECONDS = 10.0
_health_cache: tuple[float, bool] = (0.0, False)  # (expires_at, ready)


async def is_ready() -> bool:
    """Return True if ml-service has the model loaded.

    Result cached for 10 seconds — checking every predict call would
    be wasteful since the model only loads/unloads on container restart.
    """
    global _health_cache
    now = time.monotonic()
    expires_at, last = _health_cache
    if now < expires_at:
        return last
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{ML_SERVICE_URL}/health")
            if r.status_code != 200:
                _health_cache = (now + _HEALTH_TTL_SECONDS, False)
                return False
            data = r.json()
            ready = bool(data.get("ready"))
            _health_cache = (now + _HEALTH_TTL_SECONDS, ready)
            return ready
    except httpx.HTTPError as exc:
        logger.warning("[ml_client] health probe failed: %s", exc)
        _health_cache = (now + _HEALTH_TTL_SECONDS, False)
        return False


async def predict_batch(series_list: list[list[float]]) -> list[Optional[list[float]]]:
    """POST a batch of pre-resampled fill-level series and get forecasts.

    Each series in `series_list` MUST be exactly `CONTEXT_LENGTH` floats
    long — pad/truncate before calling.

    Returns a list of length `len(series_list)`. Each element is either:
      - a list of `PREDICTION_LENGTH` floats (the 24h forecast)
      - None, if ml-service couldn't predict that particular entry

    On total failure (network down, ml-service crashed, etc.) returns a
    list of all-None — never raises. The caller can fall back to a
    simpler heuristic if it wants.
    """
    if not series_list:
        return []

    payload = {"series": series_list}
    try:
        async with httpx.AsyncClient(timeout=ML_REQUEST_TIMEOUT) as client:
            r = await client.post(f"{ML_SERVICE_URL}/predict_batch", json=payload)
            r.raise_for_status()
            data = r.json()
            preds = data.get("predictions") or []
            elapsed_ms = data.get("elapsed_ms", 0.0)
            logger.info(
                "[ml_client] predict_batch: %d series → %d predictions in %.0f ms",
                len(series_list), sum(1 for p in preds if p is not None), elapsed_ms,
            )
            # Pad with None if ml-service returned fewer than we sent (shouldn't happen)
            if len(preds) < len(series_list):
                preds = list(preds) + [None] * (len(series_list) - len(preds))
            return preds
    except httpx.HTTPError as exc:
        logger.warning("[ml_client] predict_batch HTTP error: %s", exc)
        return [None] * len(series_list)
    except Exception as exc:
        logger.exception("[ml_client] unexpected error: %s", exc)
        return [None] * len(series_list)
