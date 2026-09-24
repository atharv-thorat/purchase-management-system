"""Supplier invoices (entry + three-way match, rematch, reject) and payments."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func

from app.api import views
from app.api.common import ERROR_RESPONSES, Allow, DateFrom, DateTo, PagingParams, in_date_range
from app.core.deps import DbSession
from app.models import Invoice, Payment, PurchaseOrder
from app.models.enums import InvoiceStatus, PaymentMode, Role
from app.schemas.common import Page, ReasonIn
from app.schemas.invoices import InvoiceDetail, InvoiceIn, InvoiceListItem, PaymentIn
from app.schemas.pos import PaymentOut
from app.services import access, invoice_service, payment_service
from app.services.invoice_service import InvoiceLineIn

router = APIRouter(tags=["invoices & payments"], responses=ERROR_RESPONSES)
READERS = access.readers(Invoice)
PAYMENT_READERS = access.readers(Payment)
A = Role.ACCOUNTS


def _load(db, invoice_id: int, user) -> Invoice:
    return access.get_visible_or_404(db, Invoice, invoice_id, user)


@router.post("/pos/{po_id}/invoices", response_model=InvoiceDetail, status_code=status.HTTP_201_CREATED)
def enter_invoice(po_id: int, body: InvoiceIn, db: DbSession, user: Allow(A)):
    """Record the supplier's invoice and run the three-way match at once. A failed match is
    not an error: the invoice comes back with status MISMATCH and `mismatch_reasons`."""
    po = access.get_visible_or_404(db, PurchaseOrder, po_id, user)
    inv = invoice_service.enter_invoice(
        db, user, po, supplier_invoice_number=body.supplier_invoice_number, invoice_date=body.invoice_date,
        total=body.total, lines=[InvoiceLineIn(ln.po_line_id, ln.qty, ln.unit_price) for ln in body.lines])
    db.commit()
    return views.invoice_detail(db, inv, user)


@router.get("/invoices", response_model=Page[InvoiceListItem])
def list_invoices(
    db: DbSession,
    user: Allow(*READERS),
    paging: PagingParams,
    status_: Annotated[list[InvoiceStatus] | None, Query(alias="status")] = None,
    supplier_id: int | None = None,
    po_id: int | None = None,
    invoice_from: DateFrom = None,
    invoice_to: DateTo = None,
    q: Annotated[str | None, Query(description="Supplier invoice number contains")] = None,
):
    stmt = access.scoped_select(Invoice, user).order_by(Invoice.id.desc())
    if status_:
        stmt = stmt.where(Invoice.status.in_(status_))
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    if po_id:
        stmt = stmt.where(Invoice.po_id == po_id)
    if q:
        stmt = stmt.where(func.lower(Invoice.supplier_invoice_number).contains(q.lower()))
    stmt = in_date_range(stmt, Invoice.invoice_date, invoice_from, invoice_to)
    return views.paginate(db, stmt, paging.page, paging.page_size, views.invoice_list_item)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: int, db: DbSession, user: Allow(*READERS)):
    return views.invoice_detail(db, _load(db, invoice_id, user), user)


@router.post("/invoices/{invoice_id}/rematch", response_model=InvoiceDetail)
def rematch_invoice(invoice_id: int, db: DbSession, user: Allow(A)):
    """Re-run the match against current GRN data (e.g. after a late delivery). Lines are not
    edited; a wrong invoice is rejected and re-entered instead (D-03)."""
    inv = _load(db, invoice_id, user)
    invoice_service.rematch_invoice(db, user, inv)
    db.commit()
    return views.invoice_detail(db, inv, user)


@router.post("/invoices/{invoice_id}/reject", response_model=InvoiceDetail)
def reject_invoice(invoice_id: int, body: ReasonIn, db: DbSession, user: Allow(A)):
    """MISMATCH → REJECTED. Frees the invoice number for the supplier's corrected invoice and
    may let the PO close."""
    inv = _load(db, invoice_id, user)
    invoice_service.reject_invoice(db, user, inv, reason=body.reason)
    db.commit()
    return views.invoice_detail(db, inv, user)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetail, status_code=status.HTTP_201_CREATED)
def record_payment(invoice_id: int, body: PaymentIn, db: DbSession, user: Allow(A)):
    """Partial payments allowed; never more than the balance due. Returns the invoice, whose
    `po.status` shows CLOSED if this payment settled the PO."""
    inv = _load(db, invoice_id, user)
    payment_service.record_payment(db, user, inv, amount=body.amount, mode=body.mode,
                                   reference_no=body.reference_no, paid_on=body.paid_on)
    db.commit()
    return views.invoice_detail(db, inv, user)


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentOut])
def invoice_payments(invoice_id: int, db: DbSession, user: Allow(*PAYMENT_READERS)):
    return [views.payment_out(p) for p in _load(db, invoice_id, user).payments]


@router.get("/payments", response_model=Page[PaymentOut])
def list_payments(db: DbSession, user: Allow(Role.FINANCE, A, Role.ADMIN), paging: PagingParams,
                  supplier_id: int | None = None, mode: PaymentMode | None = None, invoice_id: int | None = None,
                  paid_from: DateFrom = None, paid_to: DateTo = None):
    stmt = access.scoped_select(Payment, user).order_by(Payment.id.desc())
    if supplier_id:
        stmt = stmt.join(Invoice, Payment.invoice_id == Invoice.id).where(Invoice.supplier_id == supplier_id)
    if mode:
        stmt = stmt.where(Payment.mode == mode)
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    stmt = in_date_range(stmt, Payment.paid_on, paid_from, paid_to)
    return views.paginate(db, stmt, paging.page, paging.page_size, views.payment_out)
