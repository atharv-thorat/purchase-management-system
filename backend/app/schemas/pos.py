from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import InvoiceStatus, PaymentMode, POStatus, PRStatus
from app.schemas.common import ORM, DepartmentRef, ItemRef, SupplierRef, TimelineEntry, UserRef


class PRRef(ORM):
    id: int
    pr_number: str
    status: PRStatus
    department: DepartmentRef
    requester: UserRef


class PORef(ORM):
    id: int
    po_number: str
    status: POStatus
    supplier: SupplierRef


class POLineOut(BaseModel):
    id: int
    item: ItemRef
    qty_ordered: Decimal
    unit_price: Decimal
    line_total: Decimal
    qty_accepted: Decimal
    qty_invoiced: Decimal
    qty_pending_receipt: Decimal  # ordered − accepted
    qty_uninvoiced: Decimal  # accepted − invoiced


class POListItem(ORM):
    id: int
    po_number: str
    status: POStatus
    supplier: SupplierRef
    pr: PRRef
    total: Decimal
    created_at: datetime
    updated_at: datetime


# ---- goods receipts -----------------------------------------------------------------------------


class GRNLineIn(BaseModel):
    po_line_id: int
    qty_received: Decimal
    qty_accepted: Decimal
    qty_rejected: Decimal = Decimal("0")
    rejection_reason: str | None = None


class GRNIn(BaseModel):
    received_date: date
    remarks: str | None = None
    lines: list[GRNLineIn]


class GRNLineOut(BaseModel):
    id: int
    po_line_id: int
    item: ItemRef
    qty_received: Decimal
    qty_accepted: Decimal
    qty_rejected: Decimal
    rejection_reason: str | None


class GRNOut(BaseModel):
    id: int
    grn_number: str
    po: PORef
    received_date: date
    received_by: UserRef
    remarks: str | None
    created_at: datetime
    lines: list[GRNLineOut]


class ReceivableLine(BaseModel):
    po_line_id: int
    item: ItemRef
    qty_ordered: Decimal
    qty_accepted: Decimal
    qty_pending: Decimal


class Receivable(BaseModel):
    po: PORef
    lines: list[ReceivableLine]


# ---- invoices and payments as seen from a PO ----------------------------------------------------


class InvoiceLink(BaseModel):
    id: int
    supplier_invoice_number: str
    status: InvoiceStatus
    invoice_date: date
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal


class PaymentOut(BaseModel):
    id: int
    invoice_id: int
    supplier_invoice_number: str
    po_number: str
    supplier: SupplierRef
    amount: Decimal
    mode: PaymentMode
    reference_no: str
    paid_on: date
    recorded_by: UserRef
    created_at: datetime


class PODetail(POListItem):
    quotation_id: int
    selection_reason: str | None
    single_quote_justification: str | None
    cancel_reason: str | None
    short_close_reason: str | None
    created_by: UserRef
    lines: list[POLineOut]
    goods_receipts: list[GRNOut] | None  # None when the caller can't see GRNs
    invoices: list[InvoiceLink] | None  # None when the caller can't see invoices
    payments: list[PaymentOut] | None  # None when the caller can't see payments
    timeline: list[TimelineEntry]  # the PO's history, plus its invoices' when visible
    actions: list[str]
