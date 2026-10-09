"""The rules of time off: who approves what, and what happens after."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.leave import balance
from app.leave.models import Employee, LeaveRequest, LeaveStatus, Role
from app.leave.schemas import LeaveRequestIn
from app.leave.tasks import notify_decision, notify_manager
from app.shared import audit


def choose_route(employee: Employee, days: float) -> str:
    settings = get_settings()
    if days <= settings.direct_approval_max_days:
        return "direct"
    if employee.role == Role.MANAGER and days <= settings.self_approval_max_days:
        return "self"
    return "manager"


def submit_request(db: Session, employee: Employee, data: LeaveRequestIn) -> LeaveRequest:
    if not balance.has_enough(employee, data.days):
        raise HTTPException(status_code=400, detail="Not enough leave balance")
    request = LeaveRequest(employee_id=employee.id, start=data.start, end=data.end, days=data.days, reason=data.reason)
    request.route = choose_route(employee, data.days)
    db.add(request)
    db.flush()
    audit.record(db, employee.id, "submitted", f"leave:{request.id}")
    if request.route == "direct":
        approve_directly(db, request)
    elif request.route == "self":
        self_approve(db, request, employee)
    else:
        notify_manager.delay(request.id)
    db.commit()
    return request


def approve_directly(db: Session, request: LeaveRequest) -> None:
    _approve(db, request, approver_id=None)


def self_approve(db: Session, request: LeaveRequest, manager: Employee) -> None:
    _approve(db, request, approver_id=manager.id)


def approve_by_manager(db: Session, request: LeaveRequest, manager: Employee) -> LeaveRequest:
    _check_reviewer(request, manager)
    _approve(db, request, approver_id=manager.id)
    db.commit()
    return request


def reject_by_manager(db: Session, request: LeaveRequest, manager: Employee) -> LeaveRequest:
    _check_reviewer(request, manager)
    request.status = LeaveStatus.REJECTED
    request.decided_by = manager.id
    audit.record(db, manager.id, "rejected", f"leave:{request.id}")
    notify_decision.delay(request.id)
    db.commit()
    return request


def _check_reviewer(request: LeaveRequest, manager: Employee) -> None:
    if request.status != LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail="Already decided")
    if manager.role != Role.HR and request.employee.manager_id != manager.id:
        raise HTTPException(status_code=403, detail="Not your team member")


def _approve(db: Session, request: LeaveRequest, approver_id: int | None) -> None:
    request.status = LeaveStatus.APPROVED
    request.decided_by = approver_id
    balance.deduct(request.employee, request.days)
    audit.record(db, approver_id, "approved", f"leave:{request.id}")
    notify_decision.delay(request.id)
