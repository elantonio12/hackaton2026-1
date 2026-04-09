from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.routes.auth import require_admin
from app.core.cache import ttl_cache
from app.db.database import async_session
from app.db.models import PredictionSnapshot, User
from app.models.schemas import ContainerPrediction, ModelStatus, PredictionResponse
from app.services import ml_client
from app.services.prediction import (
    MIN_TRAINING_SAMPLES,
    _build_training_set,
    container_history,
    predict_container,
    predictor,
)

router = APIRouter()

# Read-side TTL cache for the snapshot blob. The background loop refreshes
# every 60s; this just collapses concurrent reads inside that window so we
# don't requery Postgres for the same row.
PREDICTIONS_CACHE_TTL = 5.0


async def _load_latest_snapshot() -> dict | None:
    """Fetch the most recent PredictionSnapshot row, or None if empty."""
    async with async_session() as db:
        result = await db.execute(
            select(PredictionSnapshot)
            .order_by(PredictionSnapshot.id.desc())
            .limit(1)
        )
        snap = result.scalar_one_or_none()
        if snap is None:
            return None
        return {
            "id": snap.id,
            "timestamp": snap.timestamp.isoformat() if snap.timestamp else None,
            "container_count": snap.container_count,
            "elapsed_ms": snap.elapsed_ms,
            "predictions": snap.predictions_json or [],
        }


@router.get("/", response_model=PredictionResponse)
async def get_all_predictions(zone: str | None = None, threshold: float = 0.8):
    """Return predictions from the latest background snapshot.

    Predictions are computed every 60s by the prediction_snapshot loop
    and persisted to the prediction_snapshots table. This endpoint just
    reads the most recent row, optionally filters by zone, and applies
    the requested fill-level threshold to recompute the
    `estimated_hours_to_full` indicator.

    The threshold filter is light because the heavy work (TTM forward
    pass) already happened in the background.
    """
    snap = await ttl_cache.get_or_set(
        key="predictions:latest",
        ttl=PREDICTIONS_CACHE_TTL,
        loader=_load_latest_snapshot,
    )

    if snap is None:
        # No snapshot yet — most likely we're still in the boot window
        # before the loop has produced its first row.
        return PredictionResponse(
            predictions=[],
            model_trained=predictor.is_trained,
            model_loss=predictor.loss,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    rows = snap["predictions"]
    if zone:
        rows = [p for p in rows if p.get("zone") == zone]

    return PredictionResponse(
        predictions=[ContainerPrediction(**p) for p in rows],
        model_trained=predictor.is_trained,
        model_loss=predictor.loss,
        generated_at=snap.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    )


@router.get("/model-status", response_model=ModelStatus)
async def get_model_status():
    """Return model training metadata.

    Refreshes the ml-service ready flag from the live health probe so
    the dashboard accurately reflects whether predictions are available
    right now.
    """
    await predictor.refresh_ready()
    return ModelStatus(
        is_trained=predictor.is_trained,
        training_samples=predictor.training_samples_count,
        last_trained_at=predictor.last_trained_at.isoformat() if predictor.last_trained_at else None,
        loss=predictor.loss,
        readings_since_last_train=predictor._readings_since_last_train,
        next_retrain_in=max(0, predictor.retrain_threshold - predictor._readings_since_last_train),
    )


@router.post("/retrain")
async def force_retrain(_admin: User = Depends(require_admin)):
    """Manually trigger model retraining."""
    X, y = _build_training_set(container_history)
    if len(X) < MIN_TRAINING_SAMPLES:
        raise HTTPException(status_code=400, detail="Datos insuficientes para entrenar")
    metrics = predictor.train(X, y)
    return {"status": "retrained", **metrics}


@router.get("/{container_id}", response_model=ContainerPrediction)
async def get_container_prediction(container_id: str, threshold: float = 0.8):
    """Get detailed prediction for a single container."""
    ready = await ml_client.is_ready()
    if not ready:
        raise HTTPException(status_code=503, detail="ml-service no está listo aún")

    pred = await predict_container(container_id, threshold)
    if pred is None:
        raise HTTPException(status_code=404, detail="Contenedor no encontrado en historial")
    return ContainerPrediction(**pred)
