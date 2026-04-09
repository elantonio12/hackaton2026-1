"""ml-service: Granite TTM R2 inference HTTP API.

A tiny FastAPI app whose only job is to expose the TTM model over
HTTP. Backend POSTs pre-resampled fill-level series; we return
24h forecasts.

The model loads at startup. The single uvicorn worker is intentional
— see Dockerfile for the rationale.
"""
from __future__ import annotations

import logging
import time
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.predictor import CONTEXT_LENGTH, PREDICTION_LENGTH, predictor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="EcoRuta ML Service",
    description="Granite TTM R2 inference for fill-level forecasting",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PredictBatchRequest(BaseModel):
    series: List[List[float]] = Field(
        ...,
        description=(
            f"List of fill-level series. Each series MUST be exactly "
            f"{CONTEXT_LENGTH} floats long (already resampled to 15-min "
            f"intervals and padded by the caller)."
        ),
    )


class PredictBatchResponse(BaseModel):
    predictions: List[List[float] | None]
    elapsed_ms: float
    model: str = "granite-ttm-r2"
    fallback_used: int  # how many entries fell back to watsonx


class HealthResponse(BaseModel):
    ready: bool
    model: str
    context_length: int
    prediction_length: int
    loaded_at: str | None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    """Load the TTM model into RAM. Blocks until ready."""
    try:
        predictor.load()
    except Exception:
        logger.exception("[boot] failed to load TTM model")
        # Don't crash the app — the /health probe will report ready=False
        # and the backend will fall back to its own simpler logic.


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ready=predictor.is_ready,
        model="granite-ttm-r2",
        context_length=CONTEXT_LENGTH,
        prediction_length=PREDICTION_LENGTH,
        loaded_at=predictor.loaded_at.isoformat() if predictor.loaded_at else None,
    )


@app.post("/predict_batch", response_model=PredictBatchResponse)
async def predict_batch(req: PredictBatchRequest) -> PredictBatchResponse:
    """Run TTM inference on a batch of pre-resampled series.

    The caller (backend) is responsible for:
      - Resampling raw irregular readings to 15-min intervals
      - Padding short series to CONTEXT_LENGTH floats
      - Truncating long series to the most recent CONTEXT_LENGTH

    We just take the floats, run them through the model, and return
    the 96-step forecast for each. Stateless.
    """
    if not predictor.is_ready:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    start = time.monotonic()
    results = predictor.predict_batch(req.series)
    elapsed = (time.monotonic() - start) * 1000.0
    fallback_used = sum(1 for r, s in zip(results, req.series)
                        if r is not None and len(s) != CONTEXT_LENGTH)

    return PredictBatchResponse(
        predictions=results,
        elapsed_ms=round(elapsed, 2),
        fallback_used=fallback_used,
    )
