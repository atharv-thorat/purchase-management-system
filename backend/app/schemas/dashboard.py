from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import DepartmentRef, TimelineEntry
from app.schemas.invoices import InvoiceListItem
from app.schemas.prs import PendingApproval


class DepartmentSpendOut(BaseModel):
    department: DepartmentRef
    monthly_budget: Decimal
    committed: Decimal  # approved this month, valued at PO total where one exists (D-05)
    remaining: Decimal
    utilisation_pct: Decimal
    over_budget: bool


class PendingPaymentsOut(BaseModel):
    count: int
    total_due: Decimal
    invoices: list[InvoiceListItem]


class DashboardOut(BaseModel):
    """Widgets the caller's role doesn't use are null."""

    pending_approvals: list[PendingApproval] | None  # DEPT_HEAD, FINANCE
    my_requests: dict[str, int] | None  # REQUESTER, DEPT_HEAD: own PRs by status
    pos_by_status: dict[str, int] | None
    mismatch_invoices: list[InvoiceListItem] | None
    pending_payments: PendingPaymentsOut | None  # ACCOUNTS, FINANCE, ADMIN
    spend_vs_budget: list[DepartmentSpendOut] | None
    recent_activity: list[TimelineEntry]
