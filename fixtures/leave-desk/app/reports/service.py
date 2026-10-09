"""Monthly leave figures for HR."""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.leave.models import Employee, LeaveRequest, LeaveStatus


def approved_leave_by_person(db: Session, month_start: date, month_end: date) -> list[tuple[str, float]]:
    rows = (
        db.query(Employee.name, func.sum(LeaveRequest.days))
        .join(LeaveRequest, LeaveRequest.employee_id == Employee.id)
        .filter(LeaveRequest.status == LeaveStatus.APPROVED)
        .filter(LeaveRequest.start >= month_start, LeaveRequest.start <= month_end)
        .group_by(Employee.name)
        .all()
    )
    return [(name, float(days)) for name, days in rows]


def format_summary(rows: list[tuple[str, float]]) -> str:
    lines = [f"{name}: {days:g} day(s)" for name, days in rows]
    return "\n".join(lines) or "No approved leave this month."


def export_csv(db: Session, month_start: date, month_end: date) -> str:
    raise NotImplementedError("CSV export is planned but not built yet")
