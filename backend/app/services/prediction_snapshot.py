"""Background prediction snapshot loop.

Same pattern as services/metrics_snapshot.py but for the predictions
blob. Every PREDICTION_SNAPSHOT_INTERVAL_SECONDS the leader worker:

  1. Calls predict_all() against ml-service
  2. Persists the entire blob to the prediction_snapshots table
  3. Trims old rows so the table never grows unbounded

Why this exists:
  - The /predictions/ endpoint used to call predict_all() on every
    HTTP request. With N admin tabs polling every 20s, that's N TTM
    forward passes per window per worker.
  - Each call also returned slightly different numbers because the
    sensor simulator updates fill_levels in the background — visually
    jittery for the operator.
  - Snapshotting in the background gives one canonical answer per
    refresh window, served to every reader from the same blob.

Multi-worker safety: fcntl.flock leader election (mirror of
metrics_snapshot.py). Only the leader runs the loop; followers
return immediately so HTTP throughput is unaffected.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time

from sqlalchemy import delete, select

from app.db.database import async_session
from app.db.models import PredictionSnapshot
from app.services import ml_client
from app.services.prediction import predict_all

logger = logging.getLogger(__name__)

PREDICTION_SNAPSHOT_INTERVAL_SECONDS = int(
    os.environ.get("PREDICTION_SNAPSHOT_SECONDS", "60")
)
# Keep at most this many rows in prediction_snapshots; we only ever read
# the latest one, so older rows are cleared on each successful write.
KEEP_LAST_N_SNAPSHOTS = int(os.environ.get("PREDICTION_SNAPSHOT_KEEP", "10"))

# fcntl-based leader election. Same trick as metrics_snapshot.
LEADER_LOCK_PATH = os.environ.get(
    "PREDICTION_SNAPSHOT_LOCK_PATH", "/tmp/ecoruta-prediction-leader.lock"
)
_leader_fd: int | None = None


def _try_become_leader() -> bool:
    global _leader_fd
    try:
        fd = os.open(LEADER_LOCK_PATH, os.O_WRONLY | os.O_CREAT, 0o644)
    except OSError:
        logger.exception("[prediction_snapshot] could not open lock file")
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    except OSError:
        os.close(fd)
        logger.exception("[prediction_snapshot] flock failed")
        return False
    _leader_fd = fd
    return True


async def write_snapshot() -> PredictionSnapshot | None:
    """Compute predictions and persist them as a single row.

    Bails out gracefully if ml-service isn't ready yet — there's no
    point in writing an empty snapshot at boot.
    """
    if not await ml_client.is_ready():
        logger.info("[prediction_snapshot] ml-service not ready, skipping")
        return None

    started = time.monotonic()
    try:
        predictions = await predict_all()
    except Exception:
        logger.exception("[prediction_snapshot] predict_all failed")
        return None

    elapsed_ms = (time.monotonic() - started) * 1000.0
    if not predictions:
        logger.info("[prediction_snapshot] predict_all returned 0 rows, skipping")
        return None

    try:
        async with async_session() as db:
            snap = PredictionSnapshot(
                container_count=len(predictions),
                elapsed_ms=round(elapsed_ms, 2),
                predictions_json=predictions,
            )
            db.add(snap)
            await db.flush()  # populates snap.id

            # Trim — keep only the most recent N rows
            cutoff_q = await db.execute(
                select(PredictionSnapshot.id)
                .order_by(PredictionSnapshot.id.desc())
                .offset(KEEP_LAST_N_SNAPSHOTS)
                .limit(1)
            )
            cutoff_id = cutoff_q.scalar_one_or_none()
            if cutoff_id is not None:
                await db.execute(
                    delete(PredictionSnapshot).where(PredictionSnapshot.id <= cutoff_id)
                )

            await db.commit()
            return snap
    except Exception:
        logger.exception("[prediction_snapshot] failed to persist snapshot")
        return None


async def snapshot_loop() -> None:
    """Forever-loop that refreshes the predictions snapshot.

    Multi-worker safe: only the leader (per fcntl.flock) does the work.
    Sleeps a bit on boot so ml-service has time to load the model.
    """
    await asyncio.sleep(2)

    if not _try_become_leader():
        logger.info("[prediction_snapshot] follower worker — skipping loop")
        return

    logger.info(
        "[prediction_snapshot] leader worker — loop started, interval=%ds",
        PREDICTION_SNAPSHOT_INTERVAL_SECONDS,
    )

    # Wait for ml-service to come up before the first snapshot. The
    # backend's depends_on already gates startup, but the model load
    # itself can race with the first call.
    await asyncio.sleep(45)
    snap = await write_snapshot()
    if snap is not None:
        logger.info(
            "[prediction_snapshot] initial snapshot id=%s n=%d in %.0f ms",
            snap.id, snap.container_count, snap.elapsed_ms,
        )

    while True:
        await asyncio.sleep(PREDICTION_SNAPSHOT_INTERVAL_SECONDS)
        snap = await write_snapshot()
        if snap is not None:
            logger.info(
                "[prediction_snapshot] saved snapshot id=%s n=%d in %.0f ms",
                snap.id, snap.container_count, snap.elapsed_ms,
            )
