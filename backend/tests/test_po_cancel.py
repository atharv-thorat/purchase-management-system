"""Rule 8: cancel an ISSUED PO with no GRN (D-17); the PR returns to APPROVED (D-06)."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import POStatus, PRStatus
from app.services import po_service, quotation_service
from tests.conftest import DIGITAL, LAPTOP


def test_cancel_returns_the_pr_to_approved_and_clears_the_selection(w):
    po = w.po()
    pr, q = po.pr, po.quotation
    approved_at = pr.final_approved_at
    w.later(hours=1)
    po_service.cancel_po(w.db, w.purchase, po, reason="Supplier cannot deliver")
    assert po.status is POStatus.CANCELLED
    assert po.cancel_reason == "Supplier cannot deliver"
    assert pr.status is PRStatus.APPROVED
    assert q.is_selected is False
    assert pr.final_approved_at == approved_at  # the approval still stands
    assert w.audit(po)[-1] == ("CANCELLED", "ISSUED", "CANCELLED")
    assert w.audit(pr)[-1] == ("PO_CANCELLED", "PO_CREATED", "APPROVED")


def test_after_cancellation_a_new_po_can_be_created(w):
    po = w.po()
    pr = po.pr
    po_service.cancel_po(w.db, w.purchase, po, reason="Supplier cannot deliver")
    other = w.quote(pr, DIGITAL, {LAPTOP: "1100"})
    new_po = quotation_service.select_quotation(w.db, w.purchase, pr, other, selection_reason="First supplier dropped")
    assert new_po.po_number == "PO-0002"
    assert pr.status is PRStatus.PO_CREATED
    assert [p.status for p in pr.purchase_orders] == [POStatus.CANCELLED, POStatus.ISSUED]


def test_the_same_quotation_can_be_reselected(w):
    po = w.po()
    po_service.cancel_po(w.db, w.purchase, po, reason="Raised by mistake")
    again = quotation_service.select_quotation(w.db, w.purchase, po.pr, po.quotation, single_quote_justification="x")
    assert again.quotation is po.quotation and again.quotation.is_selected


@pytest.mark.parametrize("reason", [None, "", "  "])
def test_cancel_needs_a_reason(w, reason):
    po = w.po()
    with pytest.raises(BusinessRuleViolation, match="A cancellation reason is required"):
        po_service.cancel_po(w.db, w.purchase, po, reason=reason)


def test_any_grn_blocks_cancellation_even_if_everything_was_rejected(w):
    po = w.po()
    w.receive(po, reject={LAPTOP: ("10", "Damaged in transit")})
    assert po.status is POStatus.ISSUED  # nothing accepted
    with pytest.raises(BusinessRuleViolation, match=f"{po.po_number} cannot be cancelled: goods receipt GRN-0001"):
        po_service.cancel_po(w.db, w.purchase, po, reason="x")
    assert po.status is POStatus.ISSUED and po.pr.status is PRStatus.PO_CREATED


def test_received_po_cannot_be_cancelled(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "4"})
    with pytest.raises(InvalidTransition, match="Cannot cancel .* it is PARTIALLY_RECEIVED"):
        po_service.cancel_po(w.db, w.purchase, po, reason="x")


def test_cancelling_twice_is_an_invalid_transition(w):
    po = w.po()
    po_service.cancel_po(w.db, w.purchase, po, reason="x")
    with pytest.raises(InvalidTransition, match="it is CANCELLED"):
        po_service.cancel_po(w.db, w.purchase, po, reason="x")


@pytest.mark.parametrize("role", ["requester", "head", "finance", "store", "accounts", "admin"])
def test_only_purchase_cancels(w, role):
    po = w.po()
    with pytest.raises(Forbidden, match="Only PURCHASE users can cancel purchase orders"):
        po_service.cancel_po(w.db, getattr(w, role), po, reason="x")
