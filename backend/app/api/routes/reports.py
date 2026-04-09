from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import CitizenReport
from app.models.schemas import CitizenReport as CitizenReportSchema

router = APIRouter()


@router.post("/citizen")
async def submit_citizen_report(report: CitizenReportSchema, db: AsyncSession = Depends(get_db)):
    row = CitizenReport(
        latitude=report.latitude,
        longitude=report.longitude,
        description=report.description,
        zone=report.zone,
    )
    db.add(row)
    await db.commit()
    count = (await db.execute(select(func.count()).select_from(CitizenReport))).scalar()
    return {"status": "received", "total_reports": count}


@router.get("/citizen")
async def get_citizen_reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CitizenReport))
    return [r.to_dict() for r in result.scalars().all()]
