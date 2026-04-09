# Self-hosted OSRM router preloaded with CDMX street data.
#
# On first run the container downloads a Mexico City OSM extract from BBBike,
# preprocesses it (extract / partition / customize) and starts osrm-routed
# with the MLD algorithm. The processed graph is persisted to /data so
# subsequent restarts skip the build entirely.
#
# Required because:
#   - The greedy haversine optimizer in services/optimizer.py is not realistic
#     enough for the operational scenario (no street snapping, no real
#     distances, no real polylines for the recolector view).
#   - Hitting api.project-osrm.org from production is rate-limited and would
#     fail under matrix queries with hundreds of points (which the VRP solver
#     does on every optimization run).

FROM ghcr.io/project-osrm/osrm-backend:v5.27.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME ["/data"]
EXPOSE 5000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
