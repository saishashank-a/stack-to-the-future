"""Background jobs for leave requests."""
from app.core.database import SessionLocal
from app.leave.models import LeaveRequest
from app.shared.notifications import send_email
from app.worker import celery_app


@celery_app.task(name="leave.notify_manager")
def notify_manager(request_id: int) -> None:
    with SessionLocal() as db:
        request = db.get(LeaveRequest, request_id)
        employee = request.employee
        send_email(employee.manager.email, "Leave request to review", f"{employee.name} asked for {request.days:g} day(s) off.")


@celery_app.task(name="leave.notify_decision")
def notify_decision(request_id: int) -> None:
    with SessionLocal() as db:
        request = db.get(LeaveRequest, request_id)
        outcome = request.status.value
        send_email(request.employee.email, f"Leave {outcome}", f"Your leave from {request.start} to {request.end} was {outcome}.")
