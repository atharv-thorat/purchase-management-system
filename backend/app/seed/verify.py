"""Consistency checks over the whole database.

The seed writes history without going through workflow services, so it runs these checks and
refuses to commit if any fail. They restate the SPEC invariants that must hold at rest,
whatever path produced the data.
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, GoodsReceipt, Invoice, PurchaseOrder, PurchaseRequest, Quotation
from app.models.enums import (
    DEPARTMENT_ROLES,
    MATCHED_INVOICE_STATUSES,
    ApprovalAction,
    ApprovalLevel,
    EntityType,
    InvoiceStatus,
    POStatus,
    PRStatus,
    Role,
)
from app.services._common import line_amount

ZERO = Decimal("0")


def verify(db: Session) -> list[str]:
    problems: list[str] = []
    fail = problems.append

    # ---- purchase requests ----------------------------------------------------------------
    for pr in db.scalars(select(PurchaseRequest)):
        tag = pr.pr_number
        if not pr.lines:
            fail(f"{tag}: has no lines")
        if pr.estimated_total != sum((line_amount(ln.quantity, ln.estimated_unit_price) for ln in pr.lines), ZERO):
            fail(f"{tag}: estimated_total does not equal the sum of its lines")
        if pr.requester.role not in DEPARTMENT_ROLES or pr.department_id != pr.requester.department_id:
            fail(f"{tag}: requester must be a REQUESTER/DEPT_HEAD of the PR's department")
        live_pos = [po for po in pr.purchase_orders if po.status is not POStatus.CANCELLED]
        if len(live_pos) > 1:
            fail(f"{tag}: more than one non-cancelled PO")
        if (pr.status is PRStatus.PO_CREATED) != bool(live_pos):
            fail(f"{tag}: status {pr.status} but {len(live_pos)} live PO(s)")
        if pr.status in (PRStatus.APPROVED, PRStatus.PO_CREATED) and pr.final_approved_at is None:
            fail(f"{tag}: approved without final_approved_at")
        if pr.status is PRStatus.REJECTED and not pr.rejection_reason:
            fail(f"{tag}: REJECTED without a rejection reason")
        if pr.quotations and pr.status not in (PRStatus.APPROVED, PRStatus.PO_CREATED):
            fail(f"{tag}: has quotations but is {pr.status}")
        for log in pr.approval_logs:
            if log.approver_id == pr.requester_id:
                fail(f"{tag}: approved/rejected by its own requester")
            if log.level is ApprovalLevel.DEPT_HEAD and (
                log.approver.role is not Role.DEPT_HEAD or log.approver.department_id != pr.department_id
            ):
                fail(f"{tag}: dept-head level acted on by someone outside the department's heads")
            if log.level is ApprovalLevel.FINANCE and log.approver.role is not Role.FINANCE:
                fail(f"{tag}: finance level acted on by a non-FINANCE user")
            if pr.requester.role is Role.DEPT_HEAD and log.level is ApprovalLevel.DEPT_HEAD:
                fail(f"{tag}: dept head's own PR went through the dept-head level (D-01)")
        if pr.status is PRStatus.APPROVED and not any(
            log.action is ApprovalAction.APPROVED for log in pr.approval_logs
        ):
            fail(f"{tag}: APPROVED without an approval log entry")

    # ---- quotations -------------------------------------------------------------------------
    for q in db.scalars(select(Quotation)):
        tag = f"Quotation {q.id} ({q.pr.pr_number}, {q.supplier.name})"
        priced = sorted(ql.pr_line_id for ql in q.lines)
        if priced != sorted(ln.id for ln in q.pr.lines):
            fail(f"{tag}: must price every PR line exactly once")
        if q.total != sum((line_amount(ql.pr_line.quantity, ql.unit_price) for ql in q.lines), ZERO):
            fail(f"{tag}: total does not equal the sum of its lines")
        live_po = any(po.quotation_id == q.id and po.status is not POStatus.CANCELLED for po in q.pr.purchase_orders)
        if q.is_selected != live_po:
            fail(f"{tag}: is_selected={q.is_selected} but live PO present={live_po}")

    # ---- purchase orders --------------------------------------------------------------------
    for po in db.scalars(select(PurchaseOrder)):
        tag = po.po_number
        if po.total != sum((line_amount(pl.qty_ordered, pl.unit_price) for pl in po.lines), ZERO):
            fail(f"{tag}: total does not equal the sum of its lines")
        if po.supplier_id != po.quotation.supplier_id or po.quotation.pr_id != po.pr_id:
            fail(f"{tag}: supplier/PR differ from its quotation")
        snapshot = sorted((ql.pr_line.item_id, ql.pr_line.quantity, ql.unit_price) for ql in po.quotation.lines)
        if snapshot != sorted((pl.item_id, pl.qty_ordered, pl.unit_price) for pl in po.lines):
            fail(f"{tag}: lines are not a snapshot of the selected quotation")
        # Rule 6 as it stood when the PO was created: only quotations that existed and were
        # still valid that day count (D-50).
        created_on = po.created_at.date()
        valid_then = [q for q in po.pr.quotations if q.created_at <= po.created_at and q.valid_until >= created_on]
        if po.quotation not in valid_then:
            fail(f"{tag}: created from a quotation that had expired")
        elif len(valid_then) < 2 and not po.single_quote_justification:
            fail(f"{tag}: single valid quotation without justification")
        elif po.quotation.total > min(q.total for q in valid_then) and not po.selection_reason:
            fail(f"{tag}: non-lowest valid quotation selected without a reason")

        accepted: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for grn in po.goods_receipts:
            for gl in grn.lines:
                if gl.po_line.po_id != po.id:
                    fail(f"{grn.grn_number}: line belongs to another PO")
                accepted[gl.po_line_id] += gl.qty_accepted
        invoiced: dict[int, Decimal] = defaultdict(lambda: ZERO)
        for inv in po.invoices:
            if inv.status in MATCHED_INVOICE_STATUSES:
                for il in inv.lines:
                    invoiced[il.po_line_id] += il.qty
        for pl in po.lines:
            if pl.qty_accepted != accepted[pl.id]:
                fail(f"{tag}/{pl.item.name}: qty_accepted {pl.qty_accepted} ≠ Σ GRN accepted {accepted[pl.id]}")
            if pl.qty_invoiced != invoiced[pl.id]:
                fail(f"{tag}/{pl.item.name}: qty_invoiced {pl.qty_invoiced} ≠ Σ matched invoices {invoiced[pl.id]}")

        none_accepted = all(pl.qty_accepted == 0 for pl in po.lines)
        all_accepted = all(pl.qty_accepted == pl.qty_ordered for pl in po.lines)
        live_invoices = [inv for inv in po.invoices if inv.status is not InvoiceStatus.REJECTED]
        close_condition = all(pl.qty_invoiced == pl.qty_accepted for pl in po.lines) and all(
            inv.status is InvoiceStatus.PAID for inv in live_invoices
        )
        expected_ok = {
            POStatus.ISSUED: none_accepted,
            POStatus.PARTIALLY_RECEIVED: not none_accepted and not all_accepted,
            POStatus.FULLY_RECEIVED: all_accepted and not close_condition,
            POStatus.SHORT_CLOSED: not none_accepted and not all_accepted and not close_condition,
            POStatus.CLOSED: close_condition and (all_accepted or po.short_close_reason is not None),
            POStatus.CANCELLED: not po.goods_receipts and not po.invoices,
        }[po.status]
        if not expected_ok:
            fail(f"{tag}: status {po.status} is inconsistent with its quantities/invoices")
        if po.status is not POStatus.CANCELLED and po.pr.status is not PRStatus.PO_CREATED:
            fail(f"{tag}: live PO but its PR is {po.pr.status}")

    for grn in db.scalars(select(GoodsReceipt)):
        if grn.po.status is POStatus.CANCELLED:
            fail(f"{grn.grn_number}: GRN against a cancelled PO")

    # ---- invoices and payments --------------------------------------------------------------
    for inv in db.scalars(select(Invoice)):
        tag = f"Invoice {inv.supplier_invoice_number} (id {inv.id})"
        if inv.supplier_id != inv.po.supplier_id:
            fail(f"{tag}: supplier differs from the PO's")
        if any(il.po_line.po_id != inv.po_id for il in inv.lines):
            fail(f"{tag}: line belongs to another PO")
        if inv.status in MATCHED_INVOICE_STATUSES:
            if any(il.unit_price != il.po_line.unit_price for il in inv.lines):
                fail(f"{tag}: matched despite a price difference")
            if inv.total != sum((line_amount(il.qty, il.unit_price) for il in inv.lines), ZERO):
                fail(f"{tag}: matched despite a total that differs from its lines")
        if inv.status is InvoiceStatus.MISMATCH and not inv.mismatch_details:
            fail(f"{tag}: MISMATCH without details")
        paid = sum((p.amount for p in inv.payments), ZERO)
        expected_ok = {
            InvoiceStatus.MATCHED: paid == 0,
            InvoiceStatus.PARTIALLY_PAID: 0 < paid < inv.total,
            InvoiceStatus.PAID: paid == inv.total,
        }.get(inv.status, paid == 0)
        if not expected_ok:
            fail(f"{tag}: status {inv.status} but ₹{paid} paid of ₹{inv.total}")

    # ---- audit trail ------------------------------------------------------------------------
    current = {
        EntityType.PURCHASE_REQUEST: {pr.id: pr.status for pr in db.scalars(select(PurchaseRequest))},
        EntityType.PURCHASE_ORDER: {po.id: po.status for po in db.scalars(select(PurchaseOrder))},
        EntityType.INVOICE: {inv.id: inv.status for inv in db.scalars(select(Invoice))},
    }
    trail: dict[tuple[EntityType, int], list[AuditLog]] = defaultdict(list)
    for log in db.scalars(select(AuditLog).order_by(AuditLog.at, AuditLog.id)):
        trail[(log.entity_type, log.entity_id)].append(log)
    for entity_type, statuses in current.items():
        for entity_id, status in statuses.items():
            logs = trail.get((entity_type, entity_id), [])
            if not logs or logs[0].from_status is not None:
                fail(f"{entity_type} {entity_id}: audit trail does not start with its creation")
                continue
            for prev, nxt in zip(logs, logs[1:]):
                if nxt.from_status != prev.to_status:
                    fail(f"{entity_type} {entity_id}: audit gap {prev.to_status} → {nxt.from_status}")
            if logs[-1].to_status != status:
                fail(f"{entity_type} {entity_id}: status {status} but last audit row says {logs[-1].to_status}")

    return problems
