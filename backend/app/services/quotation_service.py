"""Quotations: add/edit/delete, comparison, and select-and-create-PO (rules 5–7)."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models.enums import AuditAction, PRStatus, Role
from app.models.master import Supplier, User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import PurchaseRequest
from app.models.quotation import Quotation, QuotationLine
from app.services import state_machine as sm
from app.services._common import (
    Problems,
    ensure_role,
    fmt_date,
    inr,
    line_amount,
    money,
    not_in_future,
    optional_text,
    require_text,
)
from app.services.po_service import create_po


@dataclass(frozen=True)
class QuoteLineIn:
    pr_line_id: int
    unit_price: Decimal | int | str


def _require_approved_pr(pr: PurchaseRequest, doing: str) -> None:
    sm.require_status(pr, {PRStatus.APPROVED}, doing)


def _check_terms(quote_date: date, valid_until: date, delivery_days: int, payment_terms: str) -> str:
    not_in_future(quote_date, "Quote date")
    if valid_until < quote_date:
        raise BusinessRuleViolation("Valid-until date cannot be before the quote date")
    if valid_until < clock.today():
        raise BusinessRuleViolation(f"This quotation already expired on {fmt_date(valid_until)}")
    if not isinstance(delivery_days, int) or isinstance(delivery_days, bool) or delivery_days < 0:
        raise BusinessRuleViolation("Delivery days must be a whole number, 0 or more")
    return require_text(payment_terms, "Payment terms")


def _build_lines(pr: PurchaseRequest, lines: list[QuoteLineIn]) -> list[QuotationLine]:
    """Rule 5 / D-15: exactly one price for every PR line; quantities always the PR's."""
    pr_lines = {ln.id: ln for ln in pr.lines}
    problems = Problems()
    built: list[QuotationLine] = []
    priced: set[int] = set()
    for line in lines:
        pr_line = pr_lines.get(line.pr_line_id)
        if pr_line is None:
            problems.add(f"Line {line.pr_line_id} is not part of {pr.pr_number}")
            continue
        if pr_line.id in priced:
            problems.add(f"{pr_line.item.name} is priced more than once")
            continue
        priced.add(pr_line.id)
        try:
            price = money(line.unit_price, f"{pr_line.item.name}: unit price")
        except BusinessRuleViolation as exc:
            problems.add(exc.message)
            continue
        built.append(QuotationLine(pr_line=pr_line, unit_price=price))
    missing = [ln.item.name for ln in pr.lines if ln.id not in priced]
    if missing:
        problems.add(f"Every line of {pr.pr_number} must be priced; missing: {', '.join(missing)}")
    problems.raise_if_any()
    return built


def _total(lines: list[QuotationLine]) -> Decimal:
    return sum((line_amount(ql.pr_line.quantity, ql.unit_price) for ql in lines), Decimal("0.00"))


def _used_by_po(db: Session, quotation: Quotation) -> PurchaseOrder | None:
    return db.scalar(select(PurchaseOrder).where(PurchaseOrder.quotation_id == quotation.id))


@atomic
def add_quotation(db: Session, actor: User, pr: PurchaseRequest, *, supplier_id: int, quote_date: date,
                  valid_until: date, delivery_days: int, payment_terms: str,
                  lines: list[QuoteLineIn]) -> Quotation:
    ensure_role(actor, Role.PURCHASE, to="record quotations")
    _require_approved_pr(pr, "add a quotation to")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise BusinessRuleViolation(f"Supplier {supplier_id} does not exist")
    if not supplier.is_active:
        raise BusinessRuleViolation(f"{supplier.name} is inactive and cannot quote")
    if any(q.supplier_id == supplier.id for q in pr.quotations):  # D-16
        raise BusinessRuleViolation(
            f"{supplier.name} has already quoted for {pr.pr_number}; edit that quotation instead"
        )
    terms = _check_terms(quote_date, valid_until, delivery_days, payment_terms)
    built = _build_lines(pr, lines)
    q = Quotation(pr=pr, supplier=supplier, quote_date=quote_date, valid_until=valid_until,
                  delivery_days=delivery_days, payment_terms=terms, created_by=actor.id)
    q.lines.extend(built)
    q.total = _total(built)
    db.add(q)
    db.flush()
    return q


@atomic
def update_quotation(db: Session, actor: User, quotation: Quotation, *, quote_date: date, valid_until: date,
                     delivery_days: int, payment_terms: str, lines: list[QuoteLineIn]) -> Quotation:
    """A revised quote from the same supplier replaces the old one (D-16). Quotations that a PO
    was created from — even a cancelled one — stay as they were for the audit trail."""
    ensure_role(actor, Role.PURCHASE, to="edit quotations")
    _require_approved_pr(quotation.pr, "edit a quotation of")
    if (po := _used_by_po(db, quotation)) is not None:
        raise BusinessRuleViolation(f"This quotation was used for {po.po_number} and can no longer be changed")
    terms = _check_terms(quote_date, valid_until, delivery_days, payment_terms)
    built = _build_lines(quotation.pr, lines)
    quotation.quote_date, quotation.valid_until = quote_date, valid_until
    quotation.delivery_days, quotation.payment_terms = delivery_days, terms
    quotation.lines.clear()
    db.flush()
    quotation.lines.extend(built)
    quotation.total = _total(built)
    db.flush()
    return quotation


@atomic
def delete_quotation(db: Session, actor: User, quotation: Quotation) -> None:
    ensure_role(actor, Role.PURCHASE, to="delete quotations")
    _require_approved_pr(quotation.pr, "delete a quotation of")
    if (po := _used_by_po(db, quotation)) is not None:
        raise BusinessRuleViolation(f"This quotation was used for {po.po_number} and is kept for the audit trail")
    quotation.pr.quotations.remove(quotation)
    db.delete(quotation)
    db.flush()


# ---- comparison -----------------------------------------------------------------------------


def is_expired(quotation: Quotation) -> bool:
    return quotation.valid_until < clock.today()


def valid_quotations(pr: PurchaseRequest) -> list[Quotation]:
    """Quotations that have not expired: the only ones rule 6 looks at (D-50)."""
    return [q for q in pr.quotations if not is_expired(q)]


@dataclass
class ComparisonLine:
    pr_line_id: int
    item: str
    unit: str
    quantity: Decimal
    prices: dict[int, Decimal]  # quotation id → unit price, expired quotations included
    lowest: set[int]  # valid quotations with the lowest price for this line (ties included)


@dataclass
class Comparison:
    quotation_ids: list[int]
    totals: dict[int, Decimal]
    expired: set[int]
    lowest_valid_total: set[int]  # ties included; empty when every quotation has expired
    lines: list[ComparisonLine] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.quotation_ids) - len(self.expired)


def compare(pr: PurchaseRequest) -> Comparison:
    """Side-by-side view. Every quotation is shown; "lowest" (per line and in total) is judged
    among valid quotations only, since an expired one can't be selected (D-14, D-50)."""
    quotes = list(pr.quotations)
    valid_ids = {q.id for q in valid_quotations(pr)}
    totals = {q.id: q.total for q in quotes}
    best_total = min((t for qid, t in totals.items() if qid in valid_ids), default=None)
    result = Comparison(
        quotation_ids=[q.id for q in quotes],
        totals=totals,
        expired={q.id for q in quotes} - valid_ids,
        lowest_valid_total={qid for qid in valid_ids if totals[qid] == best_total},
    )
    for pr_line in pr.lines:
        prices = {q.id: ql.unit_price for q in quotes for ql in q.lines if ql.pr_line_id == pr_line.id}
        best = min((p for qid, p in prices.items() if qid in valid_ids), default=None)
        result.lines.append(
            ComparisonLine(pr_line_id=pr_line.id, item=pr_line.item.name, unit=pr_line.item.unit.value,
                           quantity=pr_line.quantity, prices=prices,
                           lowest={qid for qid, p in prices.items() if qid in valid_ids and p == best})
        )
    return result


# ---- selection ------------------------------------------------------------------------------


@atomic
def select_quotation(db: Session, actor: User, pr: PurchaseRequest, quotation: Quotation, *,
                     selection_reason: str | None = None,
                     single_quote_justification: str | None = None) -> PurchaseOrder:
    """Rule 6 checks, then the PO is created in the same action (rule 7, D-33).

    "Fewer than 2 quotations" and "not the lowest total" look only at quotations that have not
    expired (D-50)."""
    ensure_role(actor, Role.PURCHASE, to="select quotations")
    sm.check(pr, AuditAction.PO_CREATED)
    if quotation.pr_id != pr.id:
        raise BusinessRuleViolation(f"That quotation does not belong to {pr.pr_number}")
    supplier = quotation.supplier
    if is_expired(quotation):  # D-14
        raise BusinessRuleViolation(
            f"The quotation from {supplier.name} expired on {fmt_date(quotation.valid_until)} and cannot be selected"
        )
    if not supplier.is_active:
        raise BusinessRuleViolation(f"{supplier.name} is inactive and cannot be selected")

    selection_reason = optional_text(selection_reason)
    single_quote_justification = optional_text(single_quote_justification)
    valid = valid_quotations(pr)
    if len(valid) < 2 and not single_quote_justification:
        expired = len(pr.quotations) - len(valid)
        note = f" ({expired} expired quotation{'s' if expired > 1 else ''} not counted)" if expired else ""
        raise BusinessRuleViolation(
            f"{pr.pr_number} has only one valid quotation{note}; a single-quote justification is required"
        )
    cheapest = min(valid, key=lambda q: q.total)
    if quotation.total > cheapest.total and not selection_reason:
        raise BusinessRuleViolation(
            f"The quotation from {supplier.name} ({inr(quotation.total)}) is not the lowest valid one "
            f"({inr(cheapest.total)} from {cheapest.supplier.name}); a selection reason is required"
        )
    return create_po(db, actor, pr, quotation, selection_reason=selection_reason,
                     single_quote_justification=single_quote_justification)
