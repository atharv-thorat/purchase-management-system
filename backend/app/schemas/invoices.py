from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import InvoiceStatus, PaymentMode
from app.schemas.common import ItemRef, SupplierRef, TimelineEntry, UserRef
from app.schemas.pos import PaymentOut, PORef


class InvoiceLineIn(BaseModel):
    po_line_id: int
    qty: Decimal
    unit_price: Decimal


class InvoiceIn(BaseModel):
    supplier_invoice_number: str
    invoice_date: date
    total: Decimal
    lines: list[InvoiceLineIn]


class InvoiceLineOut(BaseModel):
    id: int
    po_line_id: int
    item: ItemRef
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal
    po_unit_price: Decimal
    price_matches: bool


class InvoiceListItem(BaseModel):
    id: int
    supplier_invoice_number: str
    status: InvoiceStatus
    po: PORef
    supplier: SupplierRef
    invoice_date: date
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    created_at: datetime


class InvoiceDetail(InvoiceListItem):
    lines: list[InvoiceLineOut]
    mismatch_reasons: list[str]  # one human-readable reason per failed check
    rejection_reason: str | None
    created_by: UserRef
    payments: list[PaymentOut] | None  # None when the caller can't see payments
    timeline: list[TimelineEntry]
    actions: list[str]


class PaymentIn(BaseModel):
    amount: Decimal
    mode: PaymentMode
    reference_no: str
    paid_on: date
