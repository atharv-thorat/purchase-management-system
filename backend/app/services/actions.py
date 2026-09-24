"""What the current user can do to a record right now, so the UI shows only usable buttons.

These mirror the services' guards (role, ownership, status); the services remain the only
enforcement point. ADMIN never gets an action (D-09).
"""

from app.models.enums import AuditAction as A
from app.models.enums import POStatus, PRStatus, Role
from app.models.invoice import Invoice
from app.models.master import User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.services import state_machine as sm
from app.services.invoice_service import INVOICEABLE_PO_STATUSES
from app.services.quotation_service import valid_quotations


def can_act_on_pending_pr(pr: PurchaseRequest, user: User) -> bool:
    """Mirrors pr_service._authorize_approver: the right level, the right department, not self."""
    if not user.is_active or user.id == pr.requester_id:
        return False
    if pr.status is PRStatus.PENDING_DEPT_HEAD:
        return user.role is Role.DEPT_HEAD and user.department_id == pr.department_id
    if pr.status is PRStatus.PENDING_FINANCE:
        return user.role is Role.FINANCE
    return False


def pr_actions(pr: PurchaseRequest, user: User) -> list[str]:
    if not user.is_active:
        return []
    allowed = set(sm.allowed_actions(pr))
    actions: list[str] = []
    if pr.requester_id == user.id:
        actions += [name for action, name in ((A.EDITED, "edit"), (A.DELETED, "delete"),
                                               (A.SUBMITTED, "submit"), (A.RESUBMITTED, "resubmit"))
                    if action in allowed]
    if can_act_on_pending_pr(pr, user):
        actions += ["approve", "reject"]
    if user.role is Role.PURCHASE and pr.status is PRStatus.APPROVED:
        actions.append("add_quotation")
        if valid_quotations(pr):
            actions.append("select_quotation")
    return actions


def po_actions(po: PurchaseOrder, user: User) -> list[str]:
    if not user.is_active:
        return []
    actions: list[str] = []
    if user.role is Role.PURCHASE:
        if po.status is POStatus.ISSUED and not po.goods_receipts:
            actions.append("cancel")
        if po.status is POStatus.PARTIALLY_RECEIVED:
            actions.append("short_close")
    if user.role is Role.STORE and A.GRN_RECORDED in sm.allowed_actions(po):
        actions.append("record_grn")
    if user.role is Role.ACCOUNTS and po.status in INVOICEABLE_PO_STATUSES:
        actions.append("enter_invoice")
    return actions


def invoice_actions(invoice: Invoice, user: User) -> list[str]:
    if not user.is_active or user.role is not Role.ACCOUNTS:
        return []
    allowed = set(sm.allowed_actions(invoice))
    return [name for action, name in ((A.REMATCH_REQUESTED, "rematch"), (A.REJECTED, "reject"),
                                      (A.PAYMENT_RECORDED, "record_payment"))
            if action in allowed]
