"""Rule 9: goods receipts, cumulative acceptance, and receipt status from accepted qty (D-18)."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import POStatus
from app.services import grn_service, po_service
from app.services.grn_service import GRNLineIn
from tests.conftest import LAPTOP, MOUSE, TWO_LINES

D = Decimal


def _grn(w, po, lines, received_date=None, actor=None):
    return grn_service.record_grn(w.db, actor or w.store, po, received_date=received_date or clock.today(),
                                  lines=lines)


def test_partial_then_full_receipt(w):
    po = w.po(lines=TWO_LINES)  # 10 laptops, 20 mice
    grn1 = w.receive(po, accept={LAPTOP: "4"})
    assert (grn1.grn_number, po.status) == ("GRN-0001", POStatus.PARTIALLY_RECEIVED)
    assert [pl.qty_accepted for pl in po.lines] == [D("4"), D("0")]
    w.receive(po, accept={LAPTOP: "6", MOUSE: "20"})
    assert po.status is POStatus.FULLY_RECEIVED
    assert [a for a, _, _ in w.audit(po)] == ["ISSUED", "GRN_RECORDED", "GRN_RECORDED"]
    assert w.audit(po)[-1] == ("GRN_RECORDED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED")


def test_rejected_goods_do_not_count_as_received(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "7"}, reject={LAPTOP: ("3", "Cracked screens")})
    line = po.lines[0]
    assert line.qty_accepted == D("7")
    assert po.status is POStatus.PARTIALLY_RECEIVED
    gl = po.goods_receipts[0].lines[0]
    assert (gl.qty_received, gl.qty_accepted, gl.qty_rejected, gl.rejection_reason) == \
        (D("10"), D("7"), D("3"), "Cracked screens")


def test_all_rejected_grn_leaves_the_po_issued(w):
    po = w.po()
    w.receive(po, reject={LAPTOP: ("10", "Wrong model")})
    assert po.status is POStatus.ISSUED
    assert w.audit(po)[-1] == ("GRN_RECORDED", "ISSUED", "ISSUED")


def test_over_delivery_can_be_received_if_the_excess_is_rejected(w):
    po = w.po()
    _grn(w, po, [GRNLineIn(po.lines[0].id, "12", "10", "2", "Excess over PO quantity")])
    assert po.status is POStatus.FULLY_RECEIVED


def test_accepted_plus_rejected_must_equal_received(w):
    po = w.po()
    with pytest.raises(BusinessRuleViolation, match=re.escape(f"{LAPTOP}: accepted 5 + rejected 1 must equal received 7")):
        _grn(w, po, [GRNLineIn(po.lines[0].id, "7", "5", "1", "Damaged")])


def test_rejection_needs_a_reason(w):
    po = w.po()
    with pytest.raises(BusinessRuleViolation, match="a reason is required for the 2 rejected"):
        _grn(w, po, [GRNLineIn(po.lines[0].id, "5", "3", "2", " ")])


def test_cumulative_acceptance_cannot_exceed_the_ordered_quantity(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "7"})
    with pytest.raises(BusinessRuleViolation) as exc:
        _grn(w, po, [GRNLineIn(po.lines[0].id, "5", "5")])
    assert exc.value.message == f"{LAPTOP}: accepting 5 would bring accepted to 12, more than the 10 ordered"
    assert po.lines[0].qty_accepted == D("7")


def test_fractional_quantities_for_kg_items(w):
    po = w.po(lines=(("MS Steel Rod 12 mm", "100.5", "90"),))
    _grn(w, po, [GRNLineIn(po.lines[0].id, "60.250", "60.25")])
    assert po.lines[0].qty_accepted == D("60.250")


@pytest.mark.parametrize("case, message", [
    ("no_lines", "needs at least one line"),
    ("other_po", "is not part of"),
    ("duplicate", "appears more than once"),
    ("zero_received", "quantity received must be greater than 0"),
    ("negative_rejected", "quantity rejected cannot be negative"),
])
def test_line_validation(w, case, message):
    po, other = w.po(lines=TWO_LINES), w.po()
    laptop = po.lines[0].id
    lines = {
        "no_lines": [],
        "other_po": [GRNLineIn(other.lines[0].id, "1", "1")],
        "duplicate": [GRNLineIn(laptop, "1", "1"), GRNLineIn(laptop, "1", "1")],
        "zero_received": [GRNLineIn(laptop, "0", "0")],
        "negative_rejected": [GRNLineIn(laptop, "1", "2", "-1", "x")],
    }[case]
    with pytest.raises(BusinessRuleViolation, match=message):
        _grn(w, po, lines)


def test_received_date_cannot_be_in_the_future_or_before_the_po(w):
    po = w.po()
    line = [GRNLineIn(po.lines[0].id, "1", "1")]
    with pytest.raises(BusinessRuleViolation, match="cannot be in the future"):
        _grn(w, po, line, received_date=clock.today() + timedelta(days=1))
    with pytest.raises(BusinessRuleViolation, match=f"is before {po.po_number} was issued"):
        _grn(w, po, line, received_date=clock.today() - timedelta(days=1))


@pytest.mark.parametrize("setup", ["full", "cancelled", "short_closed"])
def test_grn_only_on_issued_or_partially_received_pos(w, setup):
    po = w.po()
    if setup == "full":
        w.receive(po)
    elif setup == "cancelled":
        po_service.cancel_po(w.db, w.purchase, po, reason="x")
    else:
        w.receive(po, accept={LAPTOP: "1"})
        po_service.short_close_po(w.db, w.purchase, po, reason="x")
    with pytest.raises(InvalidTransition, match=f"Cannot record a goods receipt against .* it is {po.status}"):
        _grn(w, po, [GRNLineIn(po.lines[0].id, "1", "1")])


@pytest.mark.parametrize("role", ["requester", "head", "finance", "purchase", "accounts", "admin"])
def test_only_store_records_receipts(w, role):
    po = w.po()
    with pytest.raises(Forbidden, match="Only STORE users can record goods receipts"):
        _grn(w, po, [GRNLineIn(po.lines[0].id, "1", "1")], actor=getattr(w, role))


def test_receivable_prefill_shows_pending_quantities(w):
    po = w.po(lines=TWO_LINES)
    w.receive(po, accept={LAPTOP: "4"})
    assert [(r.po_line.item.name, r.pending) for r in grn_service.receivable(po)] == \
        [(LAPTOP, D("6")), (MOUSE, D("20"))]


def test_a_failed_grn_changes_nothing_and_uses_no_number(w):
    po = w.po(lines=TWO_LINES)
    with pytest.raises(BusinessRuleViolation):
        _grn(w, po, [GRNLineIn(po.lines[0].id, "5", "5"), GRNLineIn(po.lines[1].id, "30", "30")])
    assert [pl.qty_accepted for pl in po.lines] == [0, 0]
    assert po.goods_receipts == [] and po.status is POStatus.ISSUED
    assert w.receive(po).grn_number == "GRN-0001"
