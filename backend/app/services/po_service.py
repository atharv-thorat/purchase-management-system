"""Purchase orders: creation with price snapshot, cancel, short-close, auto-close."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models.enums import AuditAction, DocumentType, InvoiceStatus, POStatus, PRStatus, Role
from app.models.master import User
from app.models.purchase_order import POLine, PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.models.quotation import Quotation
from app.services import state_machine as sm
from app.services._common import ensure_role, line_amount, require_text
from app.services.numbering import next_number


def create_po(db: Session, actor: User, pr: PurchaseRequest, quotation: Quotation, *,
              selection_reason: str | None, single_quote_justification: str | None) -> PurchaseOrder:
    """Issue the PO for a selected quotation. Only called from quotation_service.select_quotation,
    inside its transaction (D-33); the selection rules are checked there."""
    quotation.is_selected = True
    po = PurchaseOrder(
        po_number=next_number(db, DocumentType.PO),
        pr=pr,
        quotation=quotation,
        supplier=quotation.supplier,
        status=POStatus.ISSUED,
        selection_reason=selection_reason,
        single_quote_justification=single_quote_justification,
        created_by=actor.id,
    )
    # Rule 7: prices are copied now and never read from the quotation again.
    for ql in quotation.lines:
        po.lines.append(POLine(item=ql.pr_line.item, qty_ordered=ql.pr_line.quantity, unit_price=ql.unit_price))
    po.total = sum((line_amount(pl.qty_ordered, pl.unit_price) for pl in po.lines), Decimal("0.00"))  # D-29
    db.add(po)
    sm.create(db, po, AuditAction.ISSUED, actor,
              {"pr_number": pr.pr_number, "supplier": quotation.supplier.name, "total": str(po.total)})
    sm.transition(db, pr, AuditAction.PO_CREATED, PRStatus.PO_CREATED, actor, {"po_number": po.po_number})
    return po


@atomic
def cancel_po(db: Session, actor: User, po: PurchaseOrder, *, reason: str) -> PurchaseOrder:
    """Rule 8: only an ISSUED PO with no goods receipt at all — even one where everything was
    rejected (D-17). The PR goes back to APPROVED and its quotation selection is cleared, so a
    new quotation can be selected without re-approval (D-06)."""
    ensure_role(actor, Role.PURCHASE, to="cancel purchase orders")
    sm.check(po, AuditAction.CANCELLED)
    reason = require_text(reason, "A cancellation reason")
    if po.goods_receipts:
        numbers = ", ".join(grn.grn_number for grn in po.goods_receipts)
        raise BusinessRuleViolation(
            f"{po.po_number} cannot be cancelled: goods receipt {numbers} has been recorded against it"
        )
    po.cancel_reason = reason
    sm.transition(db, po, AuditAction.CANCELLED, POStatus.CANCELLED, actor, {"reason": reason})
    po.quotation.is_selected = False
    sm.transition(db, po.pr, AuditAction.PO_CANCELLED, PRStatus.APPROVED, actor, {"po_number": po.po_number})
    return po


@atomic
def short_close_po(db: Session, actor: User, po: PurchaseOrder, *, reason: str) -> PurchaseOrder:
    """Rule 13 / D-07: stop further receipts on a partially received PO. Accepted goods are still
    invoiced and paid; the PO closes once they are (and immediately if they already are)."""
    ensure_role(actor, Role.PURCHASE, to="short-close purchase orders")
    sm.check(po, AuditAction.SHORT_CLOSED)
    reason = require_text(reason, "A short-close reason")
    po.short_close_reason = reason
    sm.transition(db, po, AuditAction.SHORT_CLOSED, POStatus.SHORT_CLOSED, actor, {"reason": reason})
    try_auto_close(db, po, actor, trigger="short-close")
    return po


def close_condition_met(po: PurchaseOrder) -> bool:
    """Rule 14: every line's accepted quantity is invoiced (by matched invoices) and every
    invoice that isn't REJECTED is PAID. An open MISMATCH invoice therefore blocks closure."""
    fully_invoiced = all(pl.qty_invoiced == pl.qty_accepted for pl in po.lines)
    live = [inv for inv in po.invoices if inv.status is not InvoiceStatus.REJECTED]
    return fully_invoiced and all(inv.status is InvoiceStatus.PAID for inv in live)


def try_auto_close(db: Session, po: PurchaseOrder, actor: User, *, trigger: str) -> bool:
    """Checked after a payment, an invoice rejection and a short-close (D-34)."""
    if po.status not in (POStatus.FULLY_RECEIVED, POStatus.SHORT_CLOSED) or not close_condition_met(po):
        return False
    sm.transition(db, po, AuditAction.CLOSED, POStatus.CLOSED, actor, {"auto": True, "trigger": trigger})
    return True
