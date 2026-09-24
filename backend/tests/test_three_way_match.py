"""Rule 10: the three-way match (PO price × GRN accepted qty × invoice), D-04, D-20, D-21, D-25, D-35."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import InvoiceStatus
from app.services import invoice_service, po_service
from app.services.invoice_service import InvoiceLineIn
from tests.conftest import LAPTOP, MOUSE, TWO_LINES

D = Decimal


def _received(w, lines=TWO_LINES, accept=None):
    po = w.po(lines=lines)
    w.receive(po, accept=accept)
    return po


def test_invoice_matching_po_price_and_accepted_qty_is_matched(w):
    po = _received(w)
    inv = w.invoice(po)
    assert inv.status is InvoiceStatus.MATCHED
    assert inv.mismatch_details is None
    assert inv.supplier is po.supplier
    assert [pl.qty_invoiced for pl in po.lines] == [D("10"), D("20")]
    # PENDING_MATCH is transient but both hops are audited (D-35)
    assert w.audit(inv) == [("ENTERED", None, "PENDING_MATCH"), ("MATCHED", "PENDING_MATCH", "MATCHED")]


def test_price_differing_by_one_paisa_is_a_mismatch(w):
    po = _received(w)
    inv = w.invoice(po, lines={LAPTOP: ("10", "1000.01")})
    assert inv.status is InvoiceStatus.MISMATCH
    assert inv.mismatch_details == f"{LAPTOP}: unit price ₹1,000.01 does not match PO price ₹1,000.00"
    assert w.audit(inv)[-1] == ("MISMATCHED", "PENDING_MATCH", "MISMATCH")


def test_invoiced_quantity_above_accepted_is_a_mismatch(w):
    po = _received(w, accept={LAPTOP: "8"})
    inv = w.invoice(po, lines={LAPTOP: ("10", "1000")})
    assert inv.mismatch_details == f"{LAPTOP}: invoiced 10, accepted 8"


def test_already_invoiced_quantity_counts_against_accepted(w):
    po = _received(w, accept={LAPTOP: "8"})
    assert w.invoice(po, "INV-1", lines={LAPTOP: ("5", "1000")}).status is InvoiceStatus.MATCHED
    second = w.invoice(po, "INV-2", lines={LAPTOP: ("5", "1000")})
    assert second.mismatch_details == f"{LAPTOP}: invoiced 5, accepted 8, already invoiced 5 (only 3 left to invoice)"
    assert w.invoice(po, "INV-3", lines={LAPTOP: ("3", "1000")}).status is InvoiceStatus.MATCHED


def test_total_must_equal_the_sum_of_lines(w):
    po = _received(w)
    inv = w.invoice(po, lines={LAPTOP: ("10", "1000")}, total="10000.50")
    assert inv.mismatch_details == "Invoice total ₹10,000.50 does not equal the sum of its lines ₹10,000.00"


def test_every_failing_check_is_listed(w):
    po = _received(w, accept={LAPTOP: "8", MOUSE: "20"})
    inv = w.invoice(po, lines={LAPTOP: ("10", "999"), MOUSE: ("20", "101")}, total="12000")
    assert inv.mismatch_details.splitlines() == [
        f"{LAPTOP}: unit price ₹999.00 does not match PO price ₹1,000.00",
        f"{LAPTOP}: invoiced 10, accepted 8",
        f"{MOUSE}: unit price ₹101.00 does not match PO price ₹100.00",
        "Invoice total ₹12,000.00 does not equal the sum of its lines ₹12,010.00",
    ]


def test_mismatched_invoice_does_not_use_up_invoiceable_quantity(w):
    """D-04: only MATCHED invoices count, so a correct invoice still matches afterwards."""
    po = _received(w, lines=((LAPTOP, "10", "1000"),))
    bad = w.invoice(po, "INV-1", lines={LAPTOP: ("10", "1100")})
    assert bad.status is InvoiceStatus.MISMATCH
    assert po.lines[0].qty_invoiced == 0
    assert w.invoice(po, "INV-2", lines={LAPTOP: ("10", "1000")}).status is InvoiceStatus.MATCHED


def test_an_invoice_may_cover_only_some_lines(w):
    po = _received(w)
    assert w.invoice(po, lines={MOUSE: ("20", "100")}).status is InvoiceStatus.MATCHED
    assert [pl.qty_invoiced for pl in po.lines] == [D("0"), D("20")]


def test_three_way_match_is_a_pure_check(w):
    po = _received(w)
    inv = w.invoice(po, lines={LAPTOP: ("10", "1000")})
    assert invoice_service.three_way_match(inv) == [f"{LAPTOP}: invoiced 10, accepted 10, already invoiced 10 "
                                                    f"(only 0 left to invoice)"]  # re-checking counts itself


@pytest.mark.parametrize("setup", ["issued", "cancelled", "closed"])
def test_invoice_only_against_received_pos(w, setup):
    po = w.po()
    if setup == "cancelled":
        po_service.cancel_po(w.db, w.purchase, po, reason="x")
    if setup == "closed":
        w.receive(po)
        w.pay(w.invoice(po, "INV-0"))
    with pytest.raises(InvalidTransition, match=f"Cannot enter an invoice against .* it is {po.status}"):
        w.invoice(po, lines={LAPTOP: ("1", "1000")})


@pytest.mark.parametrize("case, message", [
    ("no_lines", "needs at least one line"),
    ("other_po", "is not part of"),
    ("duplicate", "appears more than once"),
    ("zero_qty", "quantity must be greater than 0"),
    ("zero_total", "Invoice total must be greater than 0"),
    ("blank_number", "Supplier invoice number is required"),
    ("future_date", "Invoice date .* cannot be in the future"),
])
def test_malformed_invoices_are_refused_not_mismatched(w, case, message):
    po, other = _received(w), w.po()
    laptop = po.lines[0].id
    kwargs = dict(supplier_invoice_number="INV-9", invoice_date=clock.today(), total="1000",
                  lines=[InvoiceLineIn(laptop, "1", "1000")])
    kwargs.update({
        "no_lines": {"lines": []},
        "other_po": {"lines": [InvoiceLineIn(other.lines[0].id, "1", "1000")]},
        "duplicate": {"lines": [InvoiceLineIn(laptop, "1", "1000"), InvoiceLineIn(laptop, "1", "1000")]},
        "zero_qty": {"lines": [InvoiceLineIn(laptop, "0", "1000")]},
        "zero_total": {"total": "0"},
        "blank_number": {"supplier_invoice_number": "  "},
        "future_date": {"invoice_date": clock.today() + timedelta(days=1)},
    }[case])
    with pytest.raises(BusinessRuleViolation, match=message):
        invoice_service.enter_invoice(w.db, w.accounts, po, **kwargs)
    assert po.invoices == []


@pytest.mark.parametrize("role", ["requester", "head", "finance", "purchase", "store", "admin"])
def test_only_accounts_enters_invoices(w, role):
    po = _received(w)
    with pytest.raises(Forbidden, match="Only ACCOUNTS users can enter supplier invoices"):
        invoice_service.enter_invoice(w.db, getattr(w, role), po, supplier_invoice_number="X",
                                      invoice_date=clock.today(), total="1", lines=[])


def test_fractional_quantities_match_against_rounded_line_amounts(w):
    """The supplier's total for 2.5 kg × ₹10.01 is ₹25.03 (25.025 rounded half up) — matched."""
    po = w.po(lines=(("MS Steel Rod 12 mm", "2.5", "10.01"),))
    assert po.total == D("25.03")
    w.receive(po)
    assert w.invoice(po, lines={"MS Steel Rod 12 mm": ("2.5", "10.01")}, total="25.03").status is InvoiceStatus.MATCHED
