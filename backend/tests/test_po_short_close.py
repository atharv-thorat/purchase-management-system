"""Rule 13 / D-07: short-close a partially received PO; invoicing continues (D-25)."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import InvoiceStatus, POStatus
from app.services import po_service
from tests.conftest import LAPTOP


def _partial(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "6"})
    return po


def test_short_close_a_partially_received_po(w):
    po = _partial(w)
    po_service.short_close_po(w.db, w.purchase, po, reason="Supplier discontinued the model")
    assert po.status is POStatus.SHORT_CLOSED
    assert po.short_close_reason == "Supplier discontinued the model"
    assert w.audit(po)[-1] == ("SHORT_CLOSED", "PARTIALLY_RECEIVED", "SHORT_CLOSED")


def test_short_close_needs_a_reason(w):
    with pytest.raises(BusinessRuleViolation, match="A short-close reason is required"):
        po_service.short_close_po(w.db, w.purchase, _partial(w), reason=" ")


@pytest.mark.parametrize("accept", [None, "10"])
def test_only_partially_received_pos_can_be_short_closed(w, accept):
    po = w.po()
    if accept:
        w.receive(po, accept={LAPTOP: accept})
    with pytest.raises(InvalidTransition, match=f"Cannot short-close .* it is {po.status}"):
        po_service.short_close_po(w.db, w.purchase, po, reason="x")


def test_no_goods_receipts_after_short_close(w):
    po = _partial(w)
    po_service.short_close_po(w.db, w.purchase, po, reason="x")
    with pytest.raises(InvalidTransition, match="Cannot record a goods receipt against .* it is SHORT_CLOSED"):
        w.receive(po, accept={LAPTOP: "4"})


def test_accepted_goods_are_still_invoiced_and_paid_after_short_close(w):
    po = _partial(w)
    po_service.short_close_po(w.db, w.purchase, po, reason="x")
    inv = w.invoice(po)
    assert inv.status is InvoiceStatus.MATCHED
    w.pay(inv)
    assert po.status is POStatus.CLOSED


def test_short_close_of_an_already_settled_po_closes_it_at_once(w):
    po = _partial(w)
    w.pay(w.invoice(po))
    assert po.status is POStatus.PARTIALLY_RECEIVED  # still waiting for goods
    po_service.short_close_po(w.db, w.purchase, po, reason="Rest not needed")
    assert po.status is POStatus.CLOSED
    assert [a for a, _, _ in w.audit(po)][-2:] == ["SHORT_CLOSED", "CLOSED"]


@pytest.mark.parametrize("role", ["requester", "head", "finance", "store", "accounts", "admin"])
def test_only_purchase_short_closes(w, role):
    po = _partial(w)
    with pytest.raises(Forbidden, match="Only PURCHASE users can short-close"):
        po_service.short_close_po(w.db, getattr(w, role), po, reason="x")
