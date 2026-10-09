"""Celery worker and schedule."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

celery_app = Celery("leave_desk", broker=get_settings().broker_url, include=["app.leave.tasks", "app.reports.tasks"])
celery_app.conf.beat_schedule = {
    "monthly-summary": {
        "task": "reports.monthly_summary",
        "schedule": crontab(day_of_month="1", hour="6", minute="0"),
    },
}
