"""HR reporting API."""
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.reports import service
from app.shared.auth import require_hr
from app.worker import celery_app

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_hr)])


@router.post("/monthly/run", status_code=202)
def run_monthly_summary():
    celery_app.send_task("reports.monthly_summary")
    return {"queued": True}


@router.get("/export", response_class=PlainTextResponse)
def export(month_start: date, month_end: date, db: Session = Depends(get_db)):
    return service.export_csv(db, month_start, month_end)
