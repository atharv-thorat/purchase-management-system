"""Read-side queries behind GET /dashboard. Every figure respects the caller's read scope."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import InvoiceStatus, PRStatus, Role
from app.models.invoice import Invoice
from app.models.master import Department, User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.services import access, pr_service
from app.services.payment_service import balance_due


@dataclass(frozen=True)
class DepartmentSpend:
    department: Department
    committed: Decimal  # D-05 figure for the current month

    @property
    def remaining(self) -> Decimal:
        return self.department.monthly_budget - self.committed

    @property
    def utilisation_pct(self) -> Decimal:
        budget = self.department.monthly_budget
        return (self.committed * 100 / budget).quantize(Decimal("0.1")) if budget else Decimal("0")

    @property
    def over_budget(self) -> bool:
        return self.committed > self.department.monthly_budget


def pending_approvals(db: Session, user: User) -> list[PurchaseRequest] | None:
    """The approval inbox widget: DEPT_HEAD and FINANCE only (None hides it for others)."""
    if user.role not in (Role.DEPT_HEAD, Role.FINANCE):
        return None
    return pr_service.pending_approvals(db, user)


def spend_vs_budget(db: Session, user: User) -> list[DepartmentSpend] | None:
    """FINANCE and ADMIN see every department; requesters and dept heads their own."""
    if user.role in (Role.FINANCE, Role.ADMIN):
        departments = list(db.scalars(select(Department).order_by(Department.name)))
    elif user.role in (Role.REQUESTER, Role.DEPT_HEAD):
        departments = [user.department]
    else:
        return None
    return [DepartmentSpend(d, pr_service.committed_this_month(db, d.id)) for d in departments]


def my_requests(db: Session, user: User) -> dict[str, int] | None:
    if user.role not in (Role.REQUESTER, Role.DEPT_HEAD):
        return None
    rows = db.execute(
        select(PurchaseRequest.status, func.count())
        .where(PurchaseRequest.requester_id == user.id)
        .group_by(PurchaseRequest.status)
    )
    counts = {status.value: 0 for status in PRStatus}
    counts.update({status.value: n for status, n in rows})
    return counts


def pos_by_status(db: Session, user: User) -> dict[str, int] | None:
    if not access.can_read(PurchaseOrder, user):
        return None
    rows = db.execute(
        select(PurchaseOrder.status, func.count())
        .where(access.visible_filter(PurchaseOrder, user))
        .group_by(PurchaseOrder.status)
    )
    return {status.value: n for status, n in rows}


def mismatch_invoices(db: Session, user: User, limit: int = 10) -> list[Invoice] | None:
    if not access.can_read(Invoice, user):
        return None
    return list(db.scalars(
        access.scoped_select(Invoice, user)
        .where(Invoice.status == InvoiceStatus.MISMATCH)
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .limit(limit)
    ))


@dataclass(frozen=True)
class PendingPayments:
    count: int
    total_due: Decimal
    invoices: list[Invoice]


def pending_payments(db: Session, user: User, limit: int = 10) -> PendingPayments | None:
    """Matched invoices with a balance due — the ACCOUNTS / FINANCE / ADMIN work queue."""
    if user.role not in (Role.ACCOUNTS, Role.FINANCE, Role.ADMIN):
        return None
    invoices = list(db.scalars(
        access.scoped_select(Invoice, user)
        .where(Invoice.status.in_([InvoiceStatus.MATCHED, InvoiceStatus.PARTIALLY_PAID]))
        .order_by(Invoice.invoice_date, Invoice.id)
    ))
    return PendingPayments(len(invoices), sum((balance_due(i) for i in invoices), Decimal("0")), invoices[:limit])


def recent_activity(db: Session, user: User, limit: int = 10) -> list[AuditLog]:
    return list(db.scalars(
        select(AuditLog)
        .where(access.audit_visible_filter(user))
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(limit)
    ))
