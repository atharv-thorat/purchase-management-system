"""Goods receipts (rule 9): validation, cumulative accepted quantity, PO receipt status."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models.enums import AuditAction, DocumentType, POStatus, Role
from app.models.goods_receipt import GoodsReceipt, GRNLine
from app.models.master import User
from app.models.purchase_order import POLine, PurchaseOrder
from app.services import state_machine as sm
from app.services._common import Problems, ensure_role, fmt_date, not_in_future, optional_text, qty, quantity
from app.services.numbering import next_number


@dataclass(frozen=True)
class GRNLineIn:
    po_line_id: int
    qty_received: Decimal | int | str
    qty_accepted: Decimal | int | str
    qty_rejected: Decimal | int | str = 0
    rejection_reason: str | None = None


@dataclass(frozen=True)
class Receivable:
    po_line: POLine
    pending: Decimal  # ordered − accepted so far


def receivable(po: PurchaseOrder) -> list[Receivable]:
    """Pre-fill for the GRN form: quantity still to be accepted per line."""
    return [Receivable(pl, pl.qty_ordered - pl.qty_accepted) for pl in po.lines]


def receipt_status(po: PurchaseOrder) -> POStatus:
    """D-18: nothing accepted → ISSUED, everything accepted → FULLY_RECEIVED, else PARTIALLY_RECEIVED."""
    if all(pl.qty_accepted == pl.qty_ordered for pl in po.lines):
        return POStatus.FULLY_RECEIVED
    if any(pl.qty_accepted > 0 for pl in po.lines):
        return POStatus.PARTIALLY_RECEIVED
    return POStatus.ISSUED


@atomic
def record_grn(db: Session, actor: User, po: PurchaseOrder, *, received_date: date, lines: list[GRNLineIn],
               remarks: str | None = None) -> GoodsReceipt:
    ensure_role(actor, Role.STORE, to="record goods receipts")
    sm.check(po, AuditAction.GRN_RECORDED)  # ISSUED / PARTIALLY_RECEIVED only
    not_in_future(received_date, "Received date")
    if received_date < po.created_at.date():
        raise BusinessRuleViolation(
            f"Received date {fmt_date(received_date)} is before {po.po_number} was issued"
        )
    if not lines:
        raise BusinessRuleViolation("A goods receipt needs at least one line")

    po_lines = {pl.id: pl for pl in po.lines}
    problems = Problems()
    accepted_now: dict[int, Decimal] = {}
    built: list[GRNLine] = []
    for line in lines:
        pl = po_lines.get(line.po_line_id)
        if pl is None:
            problems.add(f"Line {line.po_line_id} is not part of {po.po_number}")
            continue
        name = pl.item.name
        if pl.id in accepted_now:
            problems.add(f"{name} appears more than once")
            continue
        try:
            received = quantity(line.qty_received, f"{name}: quantity received")
            accepted = quantity(line.qty_accepted, f"{name}: quantity accepted", allow_zero=True)
            rejected = quantity(line.qty_rejected, f"{name}: quantity rejected", allow_zero=True)
        except BusinessRuleViolation as exc:
            problems.add(exc.message)
            continue
        accepted_now[pl.id] = accepted
        reason = optional_text(line.rejection_reason)
        if accepted + rejected != received:
            problems.add(f"{name}: accepted {qty(accepted)} + rejected {qty(rejected)} must equal "
                         f"received {qty(received)}")
        if rejected > 0 and reason is None:
            problems.add(f"{name}: a reason is required for the {qty(rejected)} rejected")
        if pl.qty_accepted + accepted > pl.qty_ordered:
            problems.add(f"{name}: accepting {qty(accepted)} would bring accepted to "
                         f"{qty(pl.qty_accepted + accepted)}, more than the {qty(pl.qty_ordered)} ordered")
        built.append(GRNLine(po_line=pl, qty_received=received, qty_accepted=accepted, qty_rejected=rejected,
                             rejection_reason=reason if rejected > 0 else None))
    problems.raise_if_any()

    grn = GoodsReceipt(grn_number=next_number(db, DocumentType.GRN), po=po, received_by=actor.id,
                       received_date=received_date, remarks=optional_text(remarks))
    grn.lines.extend(built)
    db.add(grn)
    for gl in built:
        gl.po_line.qty_accepted += gl.qty_accepted
    sm.transition(db, po, AuditAction.GRN_RECORDED, receipt_status(po), actor, {"grn_number": grn.grn_number})
    return grn
