"""Granite TTM R2 inference engine for the ml-service container.

This is the *only* place in the EcoRuta stack that loads torch and
the TTM model. Backend talks to it over HTTP — see
backend/app/services/ml_client.py.

Two paths:
  1. Local TTM R2 (zero-shot, CPU)            ← preferred
  2. IBM watsonx.ai hosted Granite TTM API    ← fallback when local
                                                inference fails or is
                                                explicitly disabled

The watsonx fallback used to live in backend; we moved it here so
backend never has to know about IBM Cloud credentials.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import numpy as np
import torch
from tsfm_public.toolkit.get_model import get_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — must match the backend's resampling assumptions
# ---------------------------------------------------------------------------

CONTEXT_LENGTH = 512       # 512 * 15min = 5.3 days of history
PREDICTION_LENGTH = 96     # 96 * 15min = 24 hours of forecast


# ---------------------------------------------------------------------------
# watsonx.ai fallback (optional)
# ---------------------------------------------------------------------------

WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID", "")
WATSONX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_TS_MODEL_ID = os.environ.get("WATSONX_TS_MODEL_ID", "ibm/granite-ttm-1536-96-r2")
FORCE_WATSONX = os.environ.get("FORCE_WATSONX_FORECAST", "0") == "1"

WATSONX_FORECAST_PATH = "/ml/v1/time_series/forecast"
WATSONX_API_VERSION = "2024-05-15"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

_iam_token: str | None = None
_iam_token_expires_at: datetime | None = None


def _watsonx_available() -> bool:
    return bool(WATSONX_API_KEY and WATSONX_PROJECT_ID)


def _get_iam_token() -> Optional[str]:
    """Exchange IBM Cloud API key for an IAM access token (cached)."""
    global _iam_token, _iam_token_expires_at
    if not WATSONX_API_KEY:
        return None
    now = datetime.now(timezone.utc)
    if (
        _iam_token
        and _iam_token_expires_at
        and now < _iam_token_expires_at - timedelta(minutes=5)
    ):
        return _iam_token
    try:
        resp = httpx.post(
            IAM_TOKEN_URL,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": WATSONX_API_KEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        _iam_token = data["access_token"]
        _iam_token_expires_at = now + timedelta(seconds=data.get("expires_in", 3600))
        logger.info("[watsonx] IAM token refreshed")
        return _iam_token
    except Exception as exc:
        logger.error("[watsonx] Failed to get IAM token: %s", exc)
        return None


def _watsonx_forecast_one(series: list[float]) -> Optional[list[float]]:
    """Single-series watsonx fallback. Returns 96 predictions or None."""
    token = _get_iam_token()
    if not token:
        return None

    # Build synthetic 15-min timestamps anchored to "now"
    now = datetime.now(timezone.utc)
    timestamps = [
        (now - timedelta(minutes=15 * (len(series) - 1 - i))).isoformat()
        for i in range(len(series))
    ]

    url = f"{WATSONX_URL}{WATSONX_FORECAST_PATH}?version={WATSONX_API_VERSION}"
    payload = {
        "model_id": WATSONX_TS_MODEL_ID,
        "project_id": WATSONX_PROJECT_ID,
        "schema": {
            "timestamp_column": "timestamp",
            "target_columns": ["fill_level"],
        },
        "data": {
            "timestamp": timestamps,
            "fill_level": series,
        },
        "parameters": {"prediction_length": PREDICTION_LENGTH},
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        preds = results[0].get("fill_level")
        if not preds:
            return None
        return [max(0.0, min(1.0, float(v))) for v in preds]
    except Exception as exc:
        logger.error("[watsonx] forecast failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Local TTM R2 model
# ---------------------------------------------------------------------------


class TTMPredictor:
    def __init__(self) -> None:
        self.model = None
        self.is_ready: bool = False
        self.loaded_at: datetime | None = None

    def load(self) -> None:
        """Load Granite TTM R2 weights into RAM. Called once at startup."""
        logger.info("[ttm] loading granite-ttm-r2 (ctx=%d, pred=%d)…",
                     CONTEXT_LENGTH, PREDICTION_LENGTH)
        self.model = get_model(
            model_path="ibm-granite/granite-timeseries-ttm-r2",
            context_length=CONTEXT_LENGTH,
            prediction_length=PREDICTION_LENGTH,
        )
        self.model.eval()
        self.is_ready = True
        self.loaded_at = datetime.now(timezone.utc)
        logger.info("[ttm] model ready")

    def predict_batch(self, series_list: list[list[float]]) -> list[list[float] | None]:
        """Run batched inference over a list of pre-resampled series.

        Each series must already be padded/truncated to CONTEXT_LENGTH
        floats by the caller (the backend does this in its prediction.py
        helpers). Returns a list of length-`PREDICTION_LENGTH` arrays
        (or None for series that we couldn't predict).

        Falls back to watsonx per-series if local inference fails or is
        forced off.
        """
        if not series_list:
            return []

        n = len(series_list)
        results: list[list[float] | None] = [None] * n

        # Path 1: local TTM
        if self.model is not None and not FORCE_WATSONX:
            try:
                # Validate shapes — drop bad ones; we'll fall through to
                # watsonx for those individual entries.
                bad_indices: list[int] = []
                clean: list[list[float]] = []
                clean_indices: list[int] = []
                for i, s in enumerate(series_list):
                    if len(s) == CONTEXT_LENGTH:
                        clean.append(s)
                        clean_indices.append(i)
                    else:
                        bad_indices.append(i)

                if clean:
                    batch = torch.tensor(clean, dtype=torch.float32).unsqueeze(-1)
                    with torch.no_grad():
                        output = self.model(batch)
                    preds = output.prediction_outputs[:, :, 0].numpy()
                    preds = np.clip(preds, 0.0, 1.0)
                    for batch_idx, orig_idx in enumerate(clean_indices):
                        results[orig_idx] = preds[batch_idx].tolist()

                if not bad_indices:
                    return results
                # else: fall through to watsonx for the malformed ones
            except Exception as exc:
                logger.warning("[ttm] batched inference failed: %s — trying watsonx", exc)

        # Path 2: watsonx per-series (fallback)
        if _watsonx_available():
            for i in range(n):
                if results[i] is None:
                    results[i] = _watsonx_forecast_one(series_list[i])

        return results


# Singleton — main.py loads and reuses
predictor = TTMPredictor()
