"""People and their leave requests."""
import enum
from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(str, enum.Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR = "hr"


class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.EMPLOYEE)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    balance_days: Mapped[float] = mapped_column(Float, default=20)

    manager: Mapped["Employee | None"] = relationship(remote_side=[id])


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    days: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[LeaveStatus] = mapped_column(Enum(LeaveStatus), default=LeaveStatus.PENDING)
    route: Mapped[str] = mapped_column(String(20), default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)

    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
