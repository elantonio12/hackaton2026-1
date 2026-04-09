from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.auth import require_admin
from app.db.models import User
from app.models.schemas import ContainerPrediction, ModelStatus, PredictionResponse
from app.services import ml_client
from app.services.prediction import (
    MIN_TRAINING_SAMPLES,
    _build_training_set,
    container_history,
    predict_all,
    predict_container,
    predictor,
)

router = APIRouter()


@router.get("/", response_model=PredictionResponse)
async def get_all_predictions(zone: str | None = None, threshold: float = 0.8):
    """Get fill-level predictions for all containers."""
    # Liveness probe against ml-service. Cached in ml_client so this
    # is essentially free on the hot path.
    ready = await ml_client.is_ready()
    if not ready:
        raise HTTPException(status_code=503, detail="ml-service no está listo aún")

    predictions = await predict_all(zone=zone, threshold=threshold)
    return PredictionResponse(
        predictions=[ContainerPrediction(**p) for p in predictions],
        model_trained=predictor.is_trained,
        model_loss=predictor.loss,
        generated_at=datetime.now(timezone.utc).isoformat(),
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
