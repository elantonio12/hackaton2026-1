from fastapi import APIRouter

from app.models.schemas import CitizenReport

router = APIRouter()

citizen_reports: list[CitizenReport] = []


@router.post("/citizen")
async def submit_citizen_report(report: CitizenReport):
    """Receive an anomaly report from a citizen."""
    citizen_reports.append(report)
    return {"status": "received", "total_reports": len(citizen_reports)}


@router.get("/citizen")
async def get_citizen_reports():
    """Get all citizen reports."""
    return citizen_reports
