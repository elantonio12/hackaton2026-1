"""Public CDMX geo lookup endpoints.

Exposed under /api/v1/cdmx/. No auth — these are pure spatial queries
against bundled geojson data, no DB access, safe for the citizen and
admin frontends to call freely.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.geo import find_alcaldia

router = APIRouter()


@router.get("/alcaldia")
async def lookup_alcaldia(
    lat: float = Query(..., description="Latitude in WGS84"),
    lon: float = Query(..., description="Longitude in WGS84"),
):
    """Return the alcaldia key containing (lat, lon), or 404 if outside CDMX.

    Used by the admin sensor/truck CRUD to auto-fill the zone dropdown
    as soon as the user enters coordinates, and by the citizen flow
    to validate that a user-reported location belongs to a real alcaldia.

    Response shape:
        { "alcaldia": "iztapalapa" }
    """
    key = find_alcaldia(lat, lon)
    if not key:
        raise HTTPException(
            status_code=404,
            detail="Las coordenadas estan fuera de la Ciudad de Mexico",
        )
    return {"alcaldia": key}
