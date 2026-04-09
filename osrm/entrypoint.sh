#!/bin/sh
# Bootstrap OSRM with CDMX data on first run, then serve forever.
#
# State machine:
#   1. If /data/cdmx.osm.pbf is missing, download it from $OSM_URL.
#   2. If /data/cdmx.osrm.fileIndex is missing, run extract / partition / customize.
#   3. Always exec osrm-routed against the processed graph.
#
# Persisted to a Docker volume so first-time setup (~3-5 minutes) only
# happens once per host.
set -e

DATA_DIR="${DATA_DIR:-/data}"
OSM_URL="${OSM_URL:-https://download.bbbike.org/osm/bbbike/MexicoCity/MexicoCity.osm.pbf}"
OSM_FILE="${DATA_DIR}/cdmx.osm.pbf"
OSRM_FILE="${DATA_DIR}/cdmx.osrm"
PROFILE="${PROFILE:-/opt/car.lua}"
PORT="${PORT:-5000}"
MAX_TABLE_SIZE="${MAX_TABLE_SIZE:-5000}"

mkdir -p "$DATA_DIR"

if [ ! -f "$OSM_FILE" ]; then
  echo "[osrm] Downloading CDMX OSM extract from $OSM_URL"
  curl -fSL --retry 3 --retry-delay 5 -o "${OSM_FILE}.tmp" "$OSM_URL"
  mv "${OSM_FILE}.tmp" "$OSM_FILE"
  ls -lh "$OSM_FILE"
else
  echo "[osrm] Using cached OSM extract: $OSM_FILE"
fi

if [ ! -f "${OSRM_FILE}.fileIndex" ]; then
  echo "[osrm] Preprocessing OSM data (extract / partition / customize)..."
  cd "$DATA_DIR"
  osrm-extract   -p "$PROFILE" cdmx.osm.pbf
  osrm-partition cdmx.osrm
  osrm-customize cdmx.osrm
  echo "[osrm] Preprocessing complete."
else
  echo "[osrm] Using cached routing graph: $OSRM_FILE"
fi

echo "[osrm] Starting osrm-routed on :$PORT (algorithm=mld, max-table-size=$MAX_TABLE_SIZE)"
exec osrm-routed \
  --algorithm mld \
  --ip 0.0.0.0 \
  --port "$PORT" \
  --max-table-size "$MAX_TABLE_SIZE" \
  "$OSRM_FILE"
