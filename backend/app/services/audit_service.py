"""Writes AuditLog rows. Called in the same transaction as the status change (D-28)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.models.audit import AuditLog
from app.models.enums import AuditAction, EntityType
from app.models.master import User


def record_status_change(
    db: Session,
    *,
    entity_type: EntityType,
    entity_id: int,
    action: AuditAction,
    from_status: StrEnum | None,
    to_status: StrEnum | None,
    user: User | None,
    details: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> AuditLog:
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value if to_status else None,
        user_id=user.id if user else None,
        at=at or now(),
        details=details,
    )
    db.add(entry)
    return entry
