"""Read visibility per role (SPEC "Read visibility", D-08, D-09, D-37).

Two kinds of refusal:
- the role cannot read this kind of record at all -> Forbidden (403);
- the role can, but this record is outside the caller's scope -> NotFound (404), so the
  caller can't tell whether it exists.

REQUESTER and DEPT_HEAD scopes are anchored on the PR: a requester sees documents linked to
their own PRs, a dept head those linked to any PR of their department.

On top of every scope, a DRAFT PR is visible only to its author (D-45).
"""

from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, false, or_, select, true
from sqlalchemy.orm import Session
from sqlalchemy.orm.interfaces import LoaderOption

from app.core.errors import Forbidden, NotFound
from app.models.audit import AuditLog
from app.models.enums import EntityType, PRStatus, Role
from app.models.goods_receipt import GoodsReceipt
from app.models.invoice import Invoice, Payment
from app.models.master import User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.models.quotation import Quotation

T = TypeVar("T")


class Scope(StrEnum):
    ALL = "ALL"
    OWN = "OWN"  # linked to a PR the user raised
    DEPARTMENT = "DEPARTMENT"  # linked to a PR of the user's department
    APPROVED_ONWARD = "APPROVED_ONWARD"  # PRs in APPROVED or PO_CREATED


R, DH, F, P, S, A, AD = (
    Role.REQUESTER,
    Role.DEPT_HEAD,
    Role.FINANCE,
    Role.PURCHASE,
    Role.STORE,
    Role.ACCOUNTS,
    Role.ADMIN,
)
ALL, OWN, DEPT = Scope.ALL, Scope.OWN, Scope.DEPARTMENT

# A role missing from a model's map cannot read that model at all.
READ_SCOPES: dict[type, dict[Role, Scope]] = {
    PurchaseRequest: {R: OWN, DH: DEPT, F: ALL, P: Scope.APPROVED_ONWARD, AD: ALL},
    Quotation: {F: ALL, P: ALL, AD: ALL},
    PurchaseOrder: {R: OWN, DH: DEPT, F: ALL, P: ALL, S: ALL, A: ALL, AD: ALL},
    GoodsReceipt: {R: OWN, DH: DEPT, P: ALL, S: ALL, A: ALL, AD: ALL},
    Invoice: {R: OWN, DH: DEPT, F: ALL, P: ALL, A: ALL, AD: ALL},
    Payment: {R: OWN, DH: DEPT, F: ALL, A: ALL, AD: ALL},
}

LABELS: dict[type, str] = {
    PurchaseRequest: "purchase request",
    Quotation: "quotation",
    PurchaseOrder: "purchase order",
    GoodsReceipt: "goods receipt",
    Invoice: "invoice",
    Payment: "payment",
}

AUDITED_MODELS: dict[EntityType, type] = {
    EntityType.PURCHASE_REQUEST: PurchaseRequest,
    EntityType.PURCHASE_ORDER: PurchaseOrder,
    EntityType.INVOICE: Invoice,
}


def _po_ids(pr_ids: Select) -> Select:
    return select(PurchaseOrder.id).where(PurchaseOrder.pr_id.in_(pr_ids))


def _invoice_ids(pr_ids: Select) -> Select:
    return select(Invoice.id).where(Invoice.po_id.in_(_po_ids(pr_ids)))


# How each model reaches its PR, given a subquery of visible PR ids.
_LINK_TO_PR: dict[type, Callable[[Select], ColumnElement[bool]]] = {
    PurchaseRequest: lambda pr_ids: PurchaseRequest.id.in_(pr_ids),
    Quotation: lambda pr_ids: Quotation.pr_id.in_(pr_ids),
    PurchaseOrder: lambda pr_ids: PurchaseOrder.pr_id.in_(pr_ids),
    GoodsReceipt: lambda pr_ids: GoodsReceipt.po_id.in_(_po_ids(pr_ids)),
    Invoice: lambda pr_ids: Invoice.po_id.in_(_po_ids(pr_ids)),
    Payment: lambda pr_ids: Payment.invoice_id.in_(_invoice_ids(pr_ids)),
}


def read_scope(model: type, user: User) -> Scope | None:
    return READ_SCOPES[model].get(user.role)


def readers(model: type) -> tuple[Role, ...]:
    """Roles with any read access to `model`; used as the route-level role check on GETs."""
    return tuple(READ_SCOPES[model])


def can_read(model: type, user: User) -> bool:
    return read_scope(model, user) is not None


def _scope_clause(model: type, user: User) -> ColumnElement[bool] | None:
    """Row restriction for `model`, or None when the user may read every row. 403 if none at all."""
    scope = read_scope(model, user)
    if scope is None:
        raise Forbidden(f"Your role ({user.role}) cannot view {LABELS[model]}s")

    clause = _pr_scope_clause(model, user, scope)
    if model is PurchaseRequest:
        drafts_private = or_(PurchaseRequest.status != PRStatus.DRAFT, PurchaseRequest.requester_id == user.id)
        clause = drafts_private if clause is None else clause & drafts_private
    return clause


def _pr_scope_clause(model: type, user: User, scope: Scope) -> ColumnElement[bool] | None:
    if scope is Scope.ALL:
        return None
    if scope is Scope.OWN:
        pr_ids = select(PurchaseRequest.id).where(PurchaseRequest.requester_id == user.id)
    elif scope is Scope.DEPARTMENT:
        pr_ids = select(PurchaseRequest.id).where(PurchaseRequest.department_id == user.department_id)
    elif scope is Scope.APPROVED_ONWARD:
        pr_ids = select(PurchaseRequest.id).where(
            PurchaseRequest.status.in_([PRStatus.APPROVED, PRStatus.PO_CREATED])
        )
    else:  # pragma: no cover - exhaustive over Scope
        raise AssertionError(scope)
    return _LINK_TO_PR[model](pr_ids)


def visible_filter(model: type, user: User) -> ColumnElement[bool]:
    """WHERE clause limiting `model` rows to what `user` may read. 403 if none at all."""
    clause = _scope_clause(model, user)
    return true() if clause is None else clause


def scoped_select(model: type[T], user: User) -> Select[tuple[T]]:
    return select(model).where(visible_filter(model, user))


def get_visible_or_404(
    db: Session,
    model: type[T],
    record_id: int,
    user: User,
    *,
    options: Sequence[LoaderOption] = (),
) -> T:
    """Load one record the user may read. Missing and out-of-scope look the same (D-37)."""
    stmt = scoped_select(model, user).where(model.id == record_id).options(*options)  # type: ignore[attr-defined]
    obj = db.execute(stmt).scalar_one_or_none()
    if obj is None:
        raise NotFound(f"{LABELS[model].capitalize()} {record_id} not found")
    return obj


def audit_visible_filter(user: User) -> ColumnElement[bool]:
    """Audit rows are readable when the entity they describe is readable."""
    clauses: list[ColumnElement[Any]] = []
    for entity_type, model in AUDITED_MODELS.items():
        if not can_read(model, user):
            continue
        of_type = AuditLog.entity_type == entity_type
        clause = _scope_clause(model, user)
        if clause is None:
            clauses.append(of_type)
        else:
            visible_ids = select(model.id).where(clause)  # type: ignore[attr-defined]
            clauses.append(of_type & AuditLog.entity_id.in_(visible_ids))
    return or_(*clauses) if clauses else false()
