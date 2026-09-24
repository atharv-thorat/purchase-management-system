"""The one place status changes are allowed (D-27).

Each entity has a table {(from_status, action): allowed target statuses}. `from_status` is None
for creation; a target of None means the record is deleted. Every status change in the
services goes through `create`, `transition` or `delete` here, which check the table and
write the AuditLog row in the same transaction (rule 15, D-28).

`require_status` guards actions that depend on a status without changing it (adding a
quotation needs an APPROVED PR, an invoice needs a received PO).
"""

from collections.abc import Collection
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import InvalidTransition
from app.models.enums import AuditAction as A
from app.models.enums import EntityType, InvoiceStatus, POStatus, PRStatus
from app.models.invoice import Invoice
from app.models.master import User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.services.audit_service import record_status_change

Status = StrEnum
Table = dict[tuple[Status | None, A], frozenset[Status | None]]


def _t(*targets: Status | None) -> frozenset[Status | None]:
    return frozenset(targets)


PR = PRStatus
PR_TRANSITIONS: Table = {
    (None, A.CREATED): _t(PR.DRAFT),
    (PR.DRAFT, A.EDITED): _t(PR.DRAFT),
    (PR.REJECTED, A.EDITED): _t(PR.REJECTED),
    (PR.DRAFT, A.DELETED): _t(None),
    # Entry state depends on who raised it (D-01).
    (PR.DRAFT, A.SUBMITTED): _t(PR.PENDING_DEPT_HEAD, PR.PENDING_FINANCE),
    # The whole chain restarts (D-02).
    (PR.REJECTED, A.RESUBMITTED): _t(PR.PENDING_DEPT_HEAD, PR.PENDING_FINANCE),
    (PR.PENDING_DEPT_HEAD, A.APPROVED): _t(PR.PENDING_FINANCE, PR.APPROVED),
    (PR.PENDING_FINANCE, A.APPROVED): _t(PR.APPROVED),
    (PR.PENDING_DEPT_HEAD, A.REJECTED): _t(PR.REJECTED),
    (PR.PENDING_FINANCE, A.REJECTED): _t(PR.REJECTED),
    (PR.APPROVED, A.PO_CREATED): _t(PR.PO_CREATED),
    (PR.PO_CREATED, A.PO_CANCELLED): _t(PR.APPROVED),  # D-06
}

PO = POStatus
PO_TRANSITIONS: Table = {
    (None, A.ISSUED): _t(PO.ISSUED),
    # Receipt status is recomputed from accepted quantity (D-18); a GRN that accepts nothing
    # leaves the status as it was.
    (PO.ISSUED, A.GRN_RECORDED): _t(PO.ISSUED, PO.PARTIALLY_RECEIVED, PO.FULLY_RECEIVED),
    (PO.PARTIALLY_RECEIVED, A.GRN_RECORDED): _t(PO.PARTIALLY_RECEIVED, PO.FULLY_RECEIVED),
    (PO.ISSUED, A.CANCELLED): _t(PO.CANCELLED),
    (PO.PARTIALLY_RECEIVED, A.SHORT_CLOSED): _t(PO.SHORT_CLOSED),  # D-07
    (PO.FULLY_RECEIVED, A.CLOSED): _t(PO.CLOSED),
    (PO.SHORT_CLOSED, A.CLOSED): _t(PO.CLOSED),
}

INV = InvoiceStatus
INVOICE_TRANSITIONS: Table = {
    (None, A.ENTERED): _t(INV.PENDING_MATCH),
    (INV.PENDING_MATCH, A.MATCHED): _t(INV.MATCHED),
    (INV.PENDING_MATCH, A.MISMATCHED): _t(INV.MISMATCH),
    (INV.MISMATCH, A.REMATCH_REQUESTED): _t(INV.PENDING_MATCH),  # D-03
    (INV.MISMATCH, A.REJECTED): _t(INV.REJECTED),
    (INV.MATCHED, A.PAYMENT_RECORDED): _t(INV.PARTIALLY_PAID, INV.PAID),
    (INV.PARTIALLY_PAID, A.PAYMENT_RECORDED): _t(INV.PARTIALLY_PAID, INV.PAID),
}

TABLES: dict[type, tuple[EntityType, Table]] = {
    PurchaseRequest: (EntityType.PURCHASE_REQUEST, PR_TRANSITIONS),
    PurchaseOrder: (EntityType.PURCHASE_ORDER, PO_TRANSITIONS),
    Invoice: (EntityType.INVOICE, INVOICE_TRANSITIONS),
}

VERBS: dict[A, str] = {
    A.CREATED: "create",
    A.EDITED: "edit",
    A.DELETED: "delete",
    A.SUBMITTED: "submit",
    A.RESUBMITTED: "resubmit",
    A.APPROVED: "approve",
    A.REJECTED: "reject",
    A.PO_CREATED: "create a purchase order for",
    A.PO_CANCELLED: "reopen",
    A.ISSUED: "issue",
    A.GRN_RECORDED: "record a goods receipt against",
    A.CANCELLED: "cancel",
    A.SHORT_CLOSED: "short-close",
    A.CLOSED: "close",
    A.ENTERED: "enter",
    A.MATCHED: "match",
    A.MISMATCHED: "mark as mismatched",
    A.REMATCH_REQUESTED: "rematch",
    A.PAYMENT_RECORDED: "record a payment against",
}


def label(entity: Any) -> str:
    if isinstance(entity, PurchaseRequest):
        return f"purchase request {entity.pr_number}"
    if isinstance(entity, PurchaseOrder):
        return f"purchase order {entity.po_number}"
    if isinstance(entity, Invoice):
        return f"invoice {entity.supplier_invoice_number}"
    raise TypeError(f"No state machine for {type(entity).__name__}")


def _table(entity: Any) -> tuple[EntityType, Table]:
    try:
        return TABLES[type(entity)]
    except KeyError:
        raise TypeError(f"No state machine for {type(entity).__name__}") from None


def _or(statuses: Collection[Any]) -> str:
    names = sorted(s.value for s in statuses if s is not None)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def allowed_actions(entity: Any) -> list[A]:
    """Actions the table allows from the entity's current status (for UI hints)."""
    _, table = _table(entity)
    return [action for (status, action) in table if status == entity.status and status is not None]


def check(entity: Any, action: A) -> frozenset[Status | None]:
    """Raise InvalidTransition unless `action` is allowed from the current status.
    Returns the allowed targets."""
    _, table = _table(entity)
    current = entity.status
    targets = table.get((current, action))
    if targets is None:
        allowed_from = [status for (status, act) in table if act == action and status is not None]
        why = f"allowed only when {_or(allowed_from)}" if allowed_from else "this action does not apply to it"
        raise InvalidTransition(f"Cannot {VERBS[action]} {label(entity)}: it is {current} ({why})")
    return targets


def _assert_target(entity: Any, action: A, target: Status | None) -> None:
    targets = check(entity, action)
    if target not in targets:
        raise InvalidTransition(
            f"Cannot {VERBS[action]} {label(entity)}: {entity.status} cannot move to {target}"
        )


def transition(
    db: Session,
    entity: Any,
    action: A,
    target: Status,
    actor: User | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Move `entity` to `target` via `action`, writing the audit row."""
    _assert_target(entity, action, target)
    entity_type, _ = _table(entity)
    from_status = entity.status
    entity.status = target
    db.flush()
    record_status_change(
        db,
        entity_type=entity_type,
        entity_id=entity.id,
        action=action,
        from_status=from_status,
        to_status=target,
        user=actor,
        details=details,
    )


def create(db: Session, entity: Any, action: A, actor: User | None, details: dict[str, Any] | None = None) -> None:
    """Audit a newly created entity (already added to the session, status set)."""
    entity_type, table = _table(entity)
    if entity.status not in table.get((None, action), frozenset()):
        raise InvalidTransition(f"Cannot {VERBS[action]} {label(entity)} in status {entity.status}")
    db.flush()
    record_status_change(
        db,
        entity_type=entity_type,
        entity_id=entity.id,
        action=action,
        from_status=None,
        to_status=entity.status,
        user=actor,
        details=details,
    )


def delete(db: Session, entity: Any, action: A, actor: User | None) -> None:
    """Audit and delete an entity whose table allows deletion from its current status."""
    _assert_target(entity, action, None)
    entity_type, _ = _table(entity)
    record_status_change(
        db,
        entity_type=entity_type,
        entity_id=entity.id,
        action=action,
        from_status=entity.status,
        to_status=None,
        user=actor,
    )
    db.delete(entity)
    db.flush()


def require_status(entity: Any, allowed: Collection[Status], doing: str) -> None:
    """Guard for actions that need a status but don't change it. `doing` completes
    "Cannot …", e.g. "add a quotation to"."""
    if entity.status not in allowed:
        raise InvalidTransition(
            f"Cannot {doing} {label(entity)}: it is {entity.status} (allowed only when {_or(allowed)})"
        )
