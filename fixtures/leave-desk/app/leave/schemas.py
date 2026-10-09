"""Shapes of leave data going in and out of the API."""
from datetime import date

from pydantic import BaseModel, model_validator

from app.leave.models import LeaveStatus


class LeaveRequestIn(BaseModel):
    start: date
    end: date
    days: float
    reason: str = ""

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class LeaveRequestOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    start: date
    end: date
    days: float
    status: LeaveStatus
    route: str
