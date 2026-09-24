"""Rule 5 (adding quotations), D-15 (computed totals, PR quantities), D-16 (one per supplier),
quotation edits/deletes and the comparison view."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models import Quotation
from app.services import master_service, po_service, quotation_service
from app.services.quotation_service import QuoteLineIn
from tests.conftest import DIGITAL, INFOLINE, LAPTOP, MOUSE, TECHNO, TWO_LINES

D = Decimal


def _add(w, pr, supplier=TECHNO, lines=None, quote_date=None, valid_until=None, delivery_days=7, terms="30 days"):
    quote_date = quote_date or clock.today()
    return quotation_service.add_quotation(
        w.db, w.purchase, pr, supplier_id=w.suppliers[supplier].id, quote_date=quote_date,
        valid_until=valid_until or quote_date + timedelta(days=30), delivery_days=delivery_days,
        payment_terms=terms, lines=lines if lines is not None else [QuoteLineIn(ln.id, "900") for ln in pr.lines])


def test_quotation_total_is_computed_from_pr_quantities(w):
    pr = w.approved(lines=TWO_LINES)  # 10 laptops, 20 mice
    q = w.quote(pr, prices={LAPTOP: "950", MOUSE: "90.50"})
    assert q.total == D("11310.00")  # 10 × 950 + 20 × 90.50
    assert [ql.pr_line.quantity for ql in q.lines] == [D("10"), D("20")]


@pytest.mark.parametrize("state", ["draft", "submitted"])
def test_quotations_need_an_approved_pr(w, state):
    pr = getattr(w, state)()
    with pytest.raises(InvalidTransition, match=f"Cannot add a quotation to .* it is {pr.status}"):
        _add(w, pr)


def test_no_quotations_once_the_po_exists(w):
    po = w.po()
    with pytest.raises(InvalidTransition, match="it is PO_CREATED"):
        _add(w, po.pr, supplier=DIGITAL)


@pytest.mark.parametrize("role", ["requester", "head", "finance", "store", "accounts", "admin"])
def test_only_purchase_records_quotations(w, role):
    pr = w.approved()
    with pytest.raises(Forbidden, match="Only PURCHASE users can record quotations"):
        quotation_service.add_quotation(w.db, getattr(w, role), pr, supplier_id=w.suppliers[TECHNO].id,
                                        quote_date=clock.today(), valid_until=clock.today(), delivery_days=1,
                                        payment_terms="x", lines=[])


def test_every_pr_line_must_be_priced(w):
    pr = w.approved(lines=TWO_LINES)
    with pytest.raises(BusinessRuleViolation, match="missing: Wireless Mouse"):
        _add(w, pr, lines=[QuoteLineIn(pr.lines[0].id, "900")])


def test_lines_from_another_pr_or_priced_twice_are_refused(w):
    pr = w.approved(lines=TWO_LINES)
    other = w.approved()
    lines = [QuoteLineIn(pr.lines[0].id, "1"), QuoteLineIn(pr.lines[0].id, "2"),
             QuoteLineIn(pr.lines[1].id, "3"), QuoteLineIn(other.lines[0].id, "4")]
    with pytest.raises(BusinessRuleViolation) as exc:
        _add(w, pr, lines=lines)
    assert "priced more than once" in exc.value.message
    assert f"is not part of {pr.pr_number}" in exc.value.message


def test_unit_price_must_be_positive(w):
    pr = w.approved()
    with pytest.raises(BusinessRuleViolation, match="unit price must be greater than 0"):
        _add(w, pr, lines=[QuoteLineIn(pr.lines[0].id, "0")])


def test_one_quotation_per_supplier_per_pr(w):
    pr = w.approved()
    _add(w, pr)
    with pytest.raises(BusinessRuleViolation, match=f"{TECHNO} has already quoted for {pr.pr_number}"):
        _add(w, pr)
    _add(w, pr, supplier=DIGITAL)  # another supplier is fine
    assert len(pr.quotations) == 2


def test_inactive_supplier_cannot_quote(w):
    master_service.update_supplier(w.db, w.admin, w.suppliers[TECHNO], is_active=False)
    with pytest.raises(BusinessRuleViolation, match="is inactive and cannot quote"):
        _add(w, w.approved())


def test_unknown_supplier(w):
    pr = w.approved()
    with pytest.raises(BusinessRuleViolation, match="Supplier 999 does not exist"):
        quotation_service.add_quotation(w.db, w.purchase, pr, supplier_id=999, quote_date=clock.today(),
                                        valid_until=clock.today(), delivery_days=1, payment_terms="x", lines=[])


@pytest.mark.parametrize("kwargs, message", [
    ({"quote_date": "tomorrow"}, "Quote date .* cannot be in the future"),
    ({"valid_until": "before_quote"}, "Valid-until date cannot be before the quote date"),
    ({"valid_until": "yesterday", "quote_date": "last_week"}, "already expired"),
    ({"delivery_days": -1}, "Delivery days must be a whole number"),
    ({"terms": " "}, "Payment terms is required"),
])
def test_quotation_terms_are_validated(w, kwargs, message):
    today = clock.today()
    dates = {"tomorrow": today + timedelta(days=1), "before_quote": today - timedelta(days=1),
             "yesterday": today - timedelta(days=1), "last_week": today - timedelta(days=7)}
    kwargs = {k: dates.get(v, v) if isinstance(v, str) and k != "terms" else v for k, v in kwargs.items()}
    with pytest.raises(BusinessRuleViolation, match=message):
        _add(w, w.approved(), **kwargs)


# ---- edit / delete ------------------------------------------------------------------------------


def test_revised_quote_replaces_prices_and_total(w):
    pr = w.approved()
    q = w.quote(pr, prices={LAPTOP: "900"})
    quotation_service.update_quotation(w.db, w.purchase, q, quote_date=clock.today(),
                                       valid_until=clock.today() + timedelta(days=10), delivery_days=3,
                                       payment_terms="Advance", lines=[QuoteLineIn(pr.lines[0].id, "850")])
    assert (q.total, q.delivery_days, len(q.lines)) == (D("8500.00"), 3, 1)


def test_quotation_used_by_a_po_is_frozen_even_after_cancellation(w):
    po = w.po()
    q = po.quotation
    po_service.cancel_po(w.db, w.purchase, po, reason="Supplier backed out")
    with pytest.raises(BusinessRuleViolation, match=f"used for {po.po_number} and can no longer be changed"):
        quotation_service.update_quotation(w.db, w.purchase, q, quote_date=clock.today(),
                                           valid_until=clock.today(), delivery_days=1, payment_terms="x",
                                           lines=[QuoteLineIn(po.pr.lines[0].id, "1")])
    with pytest.raises(BusinessRuleViolation, match="kept for the audit trail"):
        quotation_service.delete_quotation(w.db, w.purchase, q)


def test_unused_quotation_can_be_deleted(w):
    pr = w.approved()
    q = w.quote(pr)
    qid = q.id
    quotation_service.delete_quotation(w.db, w.purchase, q)
    assert w.db.get(Quotation, qid) is None
    assert pr.quotations == []


# ---- comparison ---------------------------------------------------------------------------------


def test_comparison_flags_lowest_per_line_lowest_valid_total_and_expired(w):
    pr = w.approved(lines=TWO_LINES)
    techno = w.quote(pr, TECHNO, {LAPTOP: "900", MOUSE: "120"})  # 9000 + 2400 = 11400
    digital = w.quote(pr, DIGITAL, {LAPTOP: "900", MOUSE: "80"})  # 9000 + 1600 = 10600
    infoline = w.quote(pr, INFOLINE, {LAPTOP: "850", MOUSE: "70"}, valid_days=2)  # 8500 + 1400 = 9900
    w.later(days=3)  # Infoline has expired
    cmp = quotation_service.compare(pr)
    laptop, mouse = cmp.lines
    assert laptop.prices[infoline.id] == D("850.00")  # still shown ...
    assert laptop.lowest == {techno.id, digital.id}  # ... but not "lowest"; ties all highlighted
    assert mouse.lowest == {digital.id}
    assert cmp.lowest_valid_total == {digital.id}
    assert cmp.expired == {infoline.id}
    assert (cmp.valid_count, cmp.totals[infoline.id]) == (2, D("9900.00"))


def test_comparison_when_every_quotation_has_expired(w):
    pr = w.approved()
    w.quote(pr, TECHNO, valid_days=1)
    w.later(days=2)
    cmp = quotation_service.compare(pr)
    assert (cmp.valid_count, cmp.lowest_valid_total, cmp.lines[0].lowest) == (0, set(), set())
