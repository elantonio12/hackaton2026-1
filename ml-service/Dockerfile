FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Pre-download TTM R2 weights so the container is offline-capable.
# This used to live in the backend image (~1.5 GB) — moving it here
# means the backend stays lean and ml-service owns the model lifecycle.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('ibm-granite/granite-timeseries-ttm-r2')"

COPY app /app/app

EXPOSE 8001

# Single worker on purpose: TTM model is loaded into RAM once and the
# inference path uses torch which already releases the GIL during the
# heavy computation, so multiple workers would just multiply the model
# memory footprint without improving throughput.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
