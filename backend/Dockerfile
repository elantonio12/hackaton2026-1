FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Granite TTM R2 model now lives in the ml-service container.
# Backend POSTs pre-resampled series to http://ml-service:8001/predict_batch.

COPY . .

EXPOSE 8000

# Multi-worker uvicorn: each worker is a separate Python process,
# bypassing the GIL so HTTP requests, DB queries, and DB-writing
# background tasks can run truly in parallel. Override at runtime
# with -e UVICORN_WORKERS=N if needed (e.g. low-RAM VPS → 1).
ENV UVICORN_WORKERS=2

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS}
