"""Supplier invoices: entry, three-way match (rule 10), rematch and reject (rule 10a), and the
duplicate-number check (rule 11)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models.enums import AuditAction, InvoiceStatus, POStatus, Role
from app.models.invoice import Invoice, InvoiceLine
from app.models.master import User
from app.models.purchase_order import PurchaseOrder
from app.services import state_machine as sm
from app.services._common import (
    Problems,
    ensure_role,
    inr,
    line_amount,
    money,
    not_in_future,
    qty,
    quantity,
    require_text,
)
from app.services.po_service import try_auto_close

INVOICEABLE_PO_STATUSES = (POStatus.PARTIALLY_RECEIVED, POStatus.FULLY_RECEIVED, POStatus.SHORT_CLOSED)  # D-25


@dataclass(frozen=True)
class InvoiceLineIn:
    po_line_id: int
    qty: Decimal | int | str
    unit_price: Decimal | int | str


def three_way_match(invoice: Invoice) -> list[str]:
    """Every failing check, one human-readable reason each; empty means MATCHED.

    Per line: price equals the PO price exactly (D-21), and quantity already invoiced by
    MATCHED invoices plus this one stays within the accepted quantity (D-04). Then the entered
    total must equal the sum of the lines (D-20)."""
    failures: list[str] = []
    for il in invoice.lines:
        pl = il.po_line
        name = pl.item.name
        if il.unit_price != pl.unit_price:
            failures.append(f"{name}: unit price {inr(il.unit_price)} does not match PO price {inr(pl.unit_price)}")
        if pl.qty_invoiced + il.qty > pl.qty_accepted:
            message = f"{name}: invoiced {qty(il.qty)}, accepted {qty(pl.qty_accepted)}"
            if pl.qty_invoiced:
                message += (f", already invoiced {qty(pl.qty_invoiced)} "
                            f"(only {qty(pl.qty_accepted - pl.qty_invoiced)} left to invoice)")
            failures.append(message)
    lines_total = sum((line_amount(il.qty, il.unit_price) for il in invoice.lines), Decimal("0.00"))
    if invoice.total != lines_total:
        failures.append(f"Invoice total {inr(invoice.total)} does not equal the sum of its lines {inr(lines_total)}")
    return failures


def _run_match(db: Session, invoice: Invoice, actor: User) -> Invoice:
    """PENDING_MATCH → MATCHED / MISMATCH, synchronously; both hops are audited (D-35)."""
    failures = three_way_match(invoice)
    if failures:
        invoice.mismatch_details = "\n".join(failures)
        sm.transition(db, invoice, AuditAction.MISMATCHED, InvoiceStatus.MISMATCH, actor, {"mismatches": failures})
    else:
        invoice.mismatch_details = None
        for il in invoice.lines:
            il.po_line.qty_invoiced += il.qty  # only MATCHED invoices count (D-04)
        sm.transition(db, invoice, AuditAction.MATCHED, InvoiceStatus.MATCHED, actor)
    return invoice


def find_live_duplicate(db: Session, supplier_id: int, number: str) -> Invoice | None:
    """Rule 11: same supplier, same number (ignoring case and surrounding spaces), not REJECTED."""
    return db.scalar(
        select(Invoice).where(
            Invoice.supplier_id == supplier_id,
            func.lower(Invoice.supplier_invoice_number) == number.strip().lower(),
            Invoice.status != InvoiceStatus.REJECTED,
        )
    )


@atomic
def enter_invoice(db: Session, actor: User, po: PurchaseOrder, *, supplier_invoice_number: str,
                  invoice_date: date, total, lines: list[InvoiceLineIn]) -> Invoice:
    """Record the supplier's invoice and match it at once. A failed match is a result
    (MISMATCH with reasons), not an error; malformed input is an error."""
    ensure_role(actor, Role.ACCOUNTS, to="enter supplier invoices")
    sm.require_status(po, INVOICEABLE_PO_STATUSES, "enter an invoice against")
    number = require_text(supplier_invoice_number, "Supplier invoice number")
    not_in_future(invoice_date, "Invoice date")
    total = money(total, "Invoice total")
    if (dup := find_live_duplicate(db, po.supplier_id, number)) is not None:
        raise BusinessRuleViolation(
            f"Invoice {dup.supplier_invoice_number} from {po.supplier.name} is already recorded against "
            f"{dup.po.po_number} ({dup.status})"
        )
    if not lines:
        raise BusinessRuleViolation("An invoice needs at least one line")

    po_lines = {pl.id: pl for pl in po.lines}
    problems = Problems()
    built: list[InvoiceLine] = []
    for line in lines:
        pl = po_lines.get(line.po_line_id)
        if pl is None:
            problems.add(f"Line {line.po_line_id} is not part of {po.po_number}")
            continue
        if any(b.po_line is pl for b in built):
            problems.add(f"{pl.item.name} appears more than once")
            continue
        try:
            built.append(InvoiceLine(po_line=pl, qty=quantity(line.qty, f"{pl.item.name}: quantity"),
                                     unit_price=money(line.unit_price, f"{pl.item.name}: unit price")))
        except BusinessRuleViolation as exc:
            problems.add(exc.message)
    problems.raise_if_any()

    invoice = Invoice(supplier_invoice_number=number, po=po, supplier=po.supplier, invoice_date=invoice_date,
                      total=total, status=InvoiceStatus.PENDING_MATCH, created_by=actor.id)
    invoice.lines.extend(built)
    db.add(invoice)
    sm.create(db, invoice, AuditAction.ENTERED, actor, {"po_number": po.po_number})
    return _run_match(db, invoice, actor)


@atomic
def rematch_invoice(db: Session, actor: User, invoice: Invoice) -> Invoice:
    """Re-run the match against current GRN and invoice data, e.g. after a late GRN. Lines are
    not edited; a wrong invoice is rejected and re-entered instead (D-03)."""
    ensure_role(actor, Role.ACCOUNTS, to="rematch invoices")
    sm.transition(db, invoice, AuditAction.REMATCH_REQUESTED, InvoiceStatus.PENDING_MATCH, actor)
    return _run_match(db, invoice, actor)


@atomic
def reject_invoice(db: Session, actor: User, invoice: Invoice, *, reason: str) -> Invoice:
    """MISMATCH → REJECTED (terminal). Frees the invoice number for the corrected invoice and may
    let the PO close (D-03, D-34)."""
    ensure_role(actor, Role.ACCOUNTS, to="reject invoices")
    sm.check(invoice, AuditAction.REJECTED)
    reason = require_text(reason, "A rejection reason")
    invoice.rejection_reason = reason
    sm.transition(db, invoice, AuditAction.REJECTED, InvoiceStatus.REJECTED, actor, {"reason": reason})
    try_auto_close(db, invoice.po, actor, trigger="invoice rejected")
    return invoice
