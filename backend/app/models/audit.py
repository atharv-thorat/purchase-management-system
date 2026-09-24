"""AuditLog: one row per status change (rule 15), written in the same transaction (D-28)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.enums import AuditAction, EntityType
from app.models.master import User
from app.models.types import enum_column


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[EntityType] = mapped_column(enum_column(EntityType))
    entity_id: Mapped[int]
    action: Mapped[AuditAction] = mapped_column(enum_column(AuditAction))
    from_status: Mapped[str | None] = mapped_column(String(30))  # None on creation
    to_status: Mapped[str | None] = mapped_column(String(30))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))  # the user whose action caused it
    at: Mapped[datetime] = mapped_column(default=now, index=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    user: Mapped[User | None] = relationship()
