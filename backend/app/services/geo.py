"""Geo lookup service: point-in-polygon over the 16 CDMX alcaldias.

Uses the official INEGI 2020 polygons published by Datos Abiertos CDMX
(see backend/app/data/cdmx_alcaldias.geojson, ~774 KB). Loaded once at
import time and cached as shapely geometries.

The public function `find_alcaldia(lat, lon)` returns the normalized
alcaldia key (matching the names used in `backend/app/data/cdmx_data.py`)
or None if the point falls outside CDMX. Used by:
  - POST /api/v1/sensors/register and POST /api/v1/trucks/ to validate
    that user-provided coordinates actually belong to the selected zone
    and to auto-fill the zone if not provided.
  - GET /api/v1/cdmx/alcaldia (public) so the admin frontend can suggest
    a zone as soon as the user types coordinates.

Why polygons instead of nearest-centroid: the alcaldias are very
irregular (Tlalpan and Milpa Alta are huge wedges, Iztapalapa is
oddly shaped, Cuauhtemoc is tiny). Nearest-centroid misclassifies
boundary points 5-10% of the time, which would cause spurious
422 rejections in the admin CRUD. Polygons are exact.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# The geojson uses display names with accents ("Cuauhtémoc", "Álvaro Obregón").
# The rest of the codebase uses lowercase, accent-free, underscored keys
# ("cuauhtemoc", "alvaro_obregon"). This map is the single source of truth
# for that translation. Add an entry here when a new alcaldia is created
# (won't happen — they're fixed by Mexican federal law).
NOMGEO_TO_KEY: dict[str, str] = {
    "azcapotzalco": "azcapotzalco",
    "coyoacan": "coyoacan",
    "cuajimalpa de morelos": "cuajimalpa_de_morelos",
    "gustavo a. madero": "gustavo_a_madero",
    "iztacalco": "iztacalco",
    "iztapalapa": "iztapalapa",
    "la magdalena contreras": "la_magdalena_contreras",
    "milpa alta": "milpa_alta",
    "alvaro obregon": "alvaro_obregon",
    "tlahuac": "tlahuac",
    "tlalpan": "tlalpan",
    "xochimilco": "xochimilco",
    "benito juarez": "benito_juarez",
    "cuauhtemoc": "cuauhtemoc",
    "miguel hidalgo": "miguel_hidalgo",
    "venustiano carranza": "venustiano_carranza",
}


def _normalize(name: str) -> str:
    """Strip accents and lowercase. 'Cuauhtémoc' -> 'cuauhtemoc'."""
    decomposed = unicodedata.normalize("NFKD", name)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_accents.strip().lower()


# ---------------------------------------------------------------------------
# Polygon loader
# ---------------------------------------------------------------------------

_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "cdmx_alcaldias.geojson"


@lru_cache(maxsize=1)
def _load_polygons() -> list[tuple[str, BaseGeometry]]:
    """Load the geojson once and return a list of (key, prepared_geometry).

    Each polygon is wrapped with shapely.prepared.prep() so that
    .contains() can be called repeatedly with much better performance
    than the default geometry — important because the admin CRUD may
    fire this on every coordinate edit.
    """
    if not _GEOJSON_PATH.exists():
        logger.error("[geo] alcaldias geojson not found at %s", _GEOJSON_PATH)
        return []

    with open(_GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    polygons: list[tuple[str, BaseGeometry]] = []
    for feature in data.get("features", []):
        nomgeo = feature.get("properties", {}).get("NOMGEO")
        if not nomgeo:
            continue
        key = NOMGEO_TO_KEY.get(_normalize(nomgeo))
        if not key:
            logger.warning("[geo] unknown NOMGEO: %r — add it to NOMGEO_TO_KEY", nomgeo)
            continue
        geom = shape(feature["geometry"])
        polygons.append((key, prep(geom)))

    logger.info("[geo] loaded %d alcaldia polygons", len(polygons))
    return polygons


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_alcaldia(latitude: float, longitude: float) -> Optional[str]:
    """Return the alcaldia key containing (lat, lon), or None if outside CDMX.

    Order is preserved from the geojson; the first polygon containing
    the point wins. In practice the polygons are non-overlapping so
    the order doesn't matter.
    """
    pt = Point(longitude, latitude)
    for key, prepared in _load_polygons():
        if prepared.contains(pt):
            return key
    return None


def is_inside_cdmx(latitude: float, longitude: float) -> bool:
    """Convenience: True if the point falls inside any of the 16 alcaldias."""
    return find_alcaldia(latitude, longitude) is not None
