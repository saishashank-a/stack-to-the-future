"""Append-only audit trail of who did what."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def record(db: Session, actor_id: int | None, action: str, subject: str) -> None:
    db.add(AuditEntry(actor_id=actor_id, action=action, subject=subject, at=datetime.now(timezone.utc)))
