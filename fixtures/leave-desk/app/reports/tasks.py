"""Scheduled reporting jobs."""
from datetime import date, timedelta

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.reports.service import approved_leave_by_person, format_summary
from app.shared.notifications import send_email
from app.worker import celery_app


@celery_app.task(name="reports.monthly_summary")
def monthly_summary() -> None:
    month_end = date.today().replace(day=1) - timedelta(days=1)
    month_start = month_end.replace(day=1)
    with SessionLocal() as db:
        rows = approved_leave_by_person(db, month_start, month_end)
    send_email(get_settings().hr_inbox, f"Leave summary {month_start:%B %Y}", format_summary(rows))
