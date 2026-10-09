"""Leave request API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.leave import service
from app.leave.models import Employee, LeaveRequest
from app.leave.schemas import LeaveRequestIn, LeaveRequestOut
from app.shared.auth import current_employee, require_manager

router = APIRouter(prefix="/leave", tags=["leave"])


@router.post("", response_model=LeaveRequestOut, status_code=201)
def submit_leave(data: LeaveRequestIn, employee: Employee = Depends(current_employee), db: Session = Depends(get_db)):
    return service.submit_request(db, employee, data)


@router.get("/mine", response_model=list[LeaveRequestOut])
def my_leave(employee: Employee = Depends(current_employee), db: Session = Depends(get_db)):
    return db.query(LeaveRequest).filter_by(employee_id=employee.id).all()


@router.post("/{request_id}/approve", response_model=LeaveRequestOut)
def approve_leave(request_id: int, manager: Employee = Depends(require_manager), db: Session = Depends(get_db)):
    return service.approve_by_manager(db, _get(db, request_id), manager)


@router.post("/{request_id}/reject", response_model=LeaveRequestOut)
def reject_leave(request_id: int, manager: Employee = Depends(require_manager), db: Session = Depends(get_db)):
    return service.reject_by_manager(db, _get(db, request_id), manager)


def _get(db: Session, request_id: int) -> LeaveRequest:
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="No such request")
    return request
