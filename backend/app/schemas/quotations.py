from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import PRStatus
from app.schemas.common import ORM, ItemRef, SupplierRef


class QuoteLineIn(BaseModel):
    pr_line_id: int
    unit_price: Decimal


class QuotationUpdate(BaseModel):
    quote_date: date
    valid_until: date
    delivery_days: int
    payment_terms: str
    lines: list[QuoteLineIn]


class QuotationIn(QuotationUpdate):
    supplier_id: int


class QuoteLineOut(ORM):
    id: int
    pr_line_id: int
    item: ItemRef
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class QuotationOut(ORM):
    id: int
    pr_id: int
    supplier: SupplierRef
    quote_date: date
    valid_until: date
    delivery_days: int
    payment_terms: str
    total: Decimal
    is_selected: bool
    is_expired: bool
    created_at: datetime
    lines: list[QuoteLineOut]


class SelectIn(BaseModel):
    selection_reason: str | None = None
    single_quote_justification: str | None = None


# ---- comparison ---------------------------------------------------------------------------------


class ComparisonQuotation(BaseModel):
    quotation_id: int
    supplier: SupplierRef
    total: Decimal
    delivery_days: int
    payment_terms: str
    quote_date: date
    valid_until: date
    is_expired: bool
    is_selected: bool
    is_lowest_valid_total: bool


class ComparisonCell(BaseModel):
    quotation_id: int
    unit_price: Decimal
    line_total: Decimal
    is_lowest: bool  # lowest among valid quotations for this line (ties all flagged)


class ComparisonRow(BaseModel):
    pr_line_id: int
    item: ItemRef
    quantity: Decimal
    cells: list[ComparisonCell]  # one per quotation, in the same order as `quotations`


class SelectionHints(BaseModel):
    """What rule 6 will demand when selecting (D-50: expired quotations don't count)."""

    valid_quotations: int
    single_quote_justification_required: bool
    lowest_valid_total: Decimal | None
    lowest_valid_quotation_ids: list[int]  # any other valid quotation needs a selection reason


class ComparisonOut(BaseModel):
    pr_id: int
    pr_number: str
    pr_status: PRStatus
    quotations: list[ComparisonQuotation]
    lines: list[ComparisonRow]
    selection: SelectionHints
