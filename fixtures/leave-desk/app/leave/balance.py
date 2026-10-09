"""Leave balance bookkeeping."""
from app.leave.models import Employee


def has_enough(employee: Employee, days: float) -> bool:
    return employee.balance_days >= days


def deduct(employee: Employee, days: float) -> None:
    # TODO: carry unused days over the year end instead of losing them.
    employee.balance_days -= days
