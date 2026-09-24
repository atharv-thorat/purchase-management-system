from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ApprovalAction, ApprovalLevel, POStatus, PRStatus
from app.schemas.common import ORM, DepartmentRef, ItemRef, SupplierRef, TimelineEntry, UserRef


class PRLineIn(BaseModel):
    item_id: int
    quantity: Decimal
    estimated_unit_price: Decimal


class PRIn(BaseModel):
    justification: str
    required_by: date
    lines: list[PRLineIn]


class PRLineOut(ORM):
    id: int
    item: ItemRef
    quantity: Decimal
    estimated_unit_price: Decimal
    line_total: Decimal


class ApprovalOut(ORM):
    level: ApprovalLevel
    action: ApprovalAction
    approver: UserRef
    comment: str | None
    over_budget: bool
    at: datetime


class BudgetOut(BaseModel):
    department: str
    monthly_budget: Decimal
    approved_this_month: Decimal
    this_request: Decimal
    projected: Decimal
    remaining_after: Decimal
    over_budget: bool


class POLink(ORM):
    id: int
    po_number: str
    status: POStatus
    total: Decimal
    supplier: SupplierRef


class PRListItem(ORM):
    id: int
    pr_number: str
    status: PRStatus
    requester: UserRef
    department: DepartmentRef
    justification: str
    estimated_total: Decimal
    required_by: date
    created_at: datetime
    submitted_at: datetime | None
    final_approved_at: datetime | None


class PRDetail(PRListItem):
    rejection_reason: str | None
    updated_at: datetime
    lines: list[PRLineOut]
    approvals: list[ApprovalOut]
    budget: BudgetOut | None  # shown to approvers while the PR is pending
    quotation_count: int | None  # None when the caller can't see quotations
    purchase_orders: list[POLink] | None  # None when the caller can't see POs
    timeline: list[TimelineEntry]
    actions: list[str]  # what the caller can do now: edit, submit, approve, add_quotation, ...


class PendingApproval(PRListItem):
    level: ApprovalLevel
    budget: BudgetOut
