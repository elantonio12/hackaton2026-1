FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Pre-download TTM R2 model so container never needs internet for inference
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('ibm-granite/granite-timeseries-ttm-r2')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
