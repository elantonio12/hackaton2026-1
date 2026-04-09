"""Fallback fill-level forecasting using IBM watsonx.ai Time Series API.

Calls the hosted Granite TTM model on watsonx.ai as a fallback when
the local model is unavailable or inference fails.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# watsonx.ai endpoints
WATSONX_FORECAST_PATH = "/ml/v1/time_series/forecast"
WATSONX_API_VERSION = "2024-05-15"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

# In-memory IAM token cache
_iam_token: str | None = None
_iam_token_expires_at: datetime | None = None


def is_available() -> bool:
    """Return True if watsonx credentials are configured."""
    return bool(settings.watsonx_api_key and settings.watsonx_project_id)


def _get_iam_token() -> str | None:
    """Exchange IBM Cloud API key for an IAM access token (cached)."""
    global _iam_token, _iam_token_expires_at

    if not settings.watsonx_api_key:
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
                "apikey": settings.watsonx_api_key,
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
    except Exception as e:
        logger.error("[watsonx] Failed to get IAM token: %s", e)
        return None


def forecast_fill_trajectory(
    timestamps: list[str],
    fill_levels: list[float],
    prediction_length: int = 96,
) -> list[float] | None:
    """Forecast fill levels via watsonx.ai Granite TTM API.

    Args:
        timestamps: ISO 8601 strings at regular 15-min intervals
        fill_levels: corresponding fill levels (0.0 to 1.0)
        prediction_length: number of future steps to predict (each = 15 min)

    Returns:
        List of `prediction_length` predicted fill levels, or None on failure.
    """
    if not is_available():
        logger.debug("[watsonx] Credentials not configured")
        return None

    if len(timestamps) != len(fill_levels):
        logger.error("[watsonx] timestamps/fill_levels length mismatch")
        return None

    token = _get_iam_token()
    if not token:
        return None

    url = f"{settings.watsonx_url}{WATSONX_FORECAST_PATH}?version={WATSONX_API_VERSION}"
    payload = {
        "model_id": settings.watsonx_ts_model_id,
        "project_id": settings.watsonx_project_id,
        "schema": {
            "timestamp_column": "timestamp",
            "target_columns": ["fill_level"],
        },
        "data": {
            "timestamp": timestamps,
            "fill_level": fill_levels,
        },
        "parameters": {
            "prediction_length": prediction_length,
        },
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

        # Response format: {"results": [{"fill_level": [...]}]}
        results = data.get("results", [])
        if not results:
            logger.warning("[watsonx] Empty results from API: %s", data)
            return None

        predictions = results[0].get("fill_level")
        if not predictions:
            logger.warning("[watsonx] No fill_level in results: %s", results[0])
            return None

        if len(predictions) != prediction_length:
            logger.warning(
                "[watsonx] Expected %d predictions, got %d",
                prediction_length, len(predictions),
            )

        logger.info(
            "[watsonx] Forecast received: %d steps from %s",
            len(predictions), settings.watsonx_ts_model_id,
        )
        return [max(0.0, min(1.0, float(v))) for v in predictions]

    except httpx.HTTPStatusError as e:
        logger.error(
            "[watsonx] HTTP %d: %s",
            e.response.status_code,
            e.response.text[:500],
        )
        return None
    except httpx.HTTPError as e:
        logger.error("[watsonx] HTTP error: %s", e)
        return None
    except Exception as e:
        logger.error("[watsonx] Unexpected error: %s", e)
        return None
