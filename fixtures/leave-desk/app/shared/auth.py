"""Who is calling, and what they are allowed to do."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.leave.models import Employee, Role


def current_employee(x_employee_id: int = Header(...), db: Session = Depends(get_db)) -> Employee:
    employee = db.get(Employee, x_employee_id)
    if employee is None:
        raise HTTPException(status_code=401, detail="Unknown employee")
    return employee


def require_manager(employee: Employee = Depends(current_employee)) -> Employee:
    if employee.role not in (Role.MANAGER, Role.HR):
        raise HTTPException(status_code=403, detail="Managers only")
    return employee


def require_hr(employee: Employee = Depends(current_employee)) -> Employee:
    if employee.role != Role.HR:
        raise HTTPException(status_code=403, detail="HR only")
    return employee
