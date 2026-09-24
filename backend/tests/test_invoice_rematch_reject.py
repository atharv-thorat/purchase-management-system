"""Rule 10a / D-03: MISMATCH invoices are rematched (no line edits) or rejected (terminal)."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import InvoiceStatus
from app.services import invoice_service
from tests.conftest import LAPTOP


def _short_invoice(w):
    """Invoice for 10 when only 8 have been accepted so far."""
    po = w.po()
    w.receive(po, accept={LAPTOP: "8"})
    return po, w.invoice(po, lines={LAPTOP: ("10", "1000")})


def test_rematch_after_a_late_grn_matches(w):
    po, inv = _short_invoice(w)
    assert inv.status is InvoiceStatus.MISMATCH
    w.receive(po, accept={LAPTOP: "2"})
    invoice_service.rematch_invoice(w.db, w.accounts, inv)
    assert inv.status is InvoiceStatus.MATCHED
    assert inv.mismatch_details is None
    assert po.lines[0].qty_invoiced == 10
    assert w.audit(inv)[-2:] == [("REMATCH_REQUESTED", "MISMATCH", "PENDING_MATCH"),
                                 ("MATCHED", "PENDING_MATCH", "MATCHED")]


def test_rematch_without_new_data_stays_mismatched_with_fresh_reasons(w):
    po, inv = _short_invoice(w)
    w.receive(po, accept={LAPTOP: "1"})
    invoice_service.rematch_invoice(w.db, w.accounts, inv)
    assert inv.status is InvoiceStatus.MISMATCH
    assert inv.mismatch_details == f"{LAPTOP}: invoiced 10, accepted 9"
    assert po.lines[0].qty_invoiced == 0


def test_rematch_does_not_edit_lines(w):
    _po, inv = _short_invoice(w)
    before = [(il.po_line_id, il.qty, il.unit_price) for il in inv.lines]
    invoice_service.rematch_invoice(w.db, w.accounts, inv)
    assert [(il.po_line_id, il.qty, il.unit_price) for il in inv.lines] == before


def test_only_mismatched_invoices_can_be_rematched(w):
    po = w.po()
    w.receive(po)
    inv = w.invoice(po)
    with pytest.raises(InvalidTransition, match="Cannot rematch invoice INV-001: it is MATCHED"):
        invoice_service.rematch_invoice(w.db, w.accounts, inv)


def test_reject_needs_a_reason_and_is_terminal(w):
    _po, inv = _short_invoice(w)
    with pytest.raises(BusinessRuleViolation, match="A rejection reason is required"):
        invoice_service.reject_invoice(w.db, w.accounts, inv, reason="")
    invoice_service.reject_invoice(w.db, w.accounts, inv, reason="Supplier to reissue for 8 units")
    assert inv.status is InvoiceStatus.REJECTED
    assert inv.rejection_reason == "Supplier to reissue for 8 units"
    assert w.audit(inv)[-1] == ("REJECTED", "MISMATCH", "REJECTED")
    with pytest.raises(InvalidTransition, match="it is REJECTED"):
        invoice_service.rematch_invoice(w.db, w.accounts, inv)
    with pytest.raises(InvalidTransition, match="it is REJECTED"):
        w.pay(inv, "1")


def test_corrected_invoice_is_entered_fresh_after_rejection(w):
    po, inv = _short_invoice(w)
    invoice_service.reject_invoice(w.db, w.accounts, inv, reason="Wrong quantity")
    corrected = w.invoice(po, lines={LAPTOP: ("8", "1000")})  # same number INV-001 (D-03)
    assert corrected.status is InvoiceStatus.MATCHED
    assert po.lines[0].qty_invoiced == 8


def test_matched_invoice_cannot_be_rejected(w):
    po = w.po()
    w.receive(po)
    inv = w.invoice(po)
    with pytest.raises(InvalidTransition, match="Cannot reject invoice INV-001: it is MATCHED"):
        invoice_service.reject_invoice(w.db, w.accounts, inv, reason="x")


@pytest.mark.parametrize("role", ["requester", "head", "finance", "purchase", "store", "admin"])
def test_only_accounts_rematches_or_rejects(w, role):
    _po, inv = _short_invoice(w)
    with pytest.raises(Forbidden, match="Only ACCOUNTS users can rematch invoices"):
        invoice_service.rematch_invoice(w.db, getattr(w, role), inv)
    with pytest.raises(Forbidden, match="Only ACCOUNTS users can reject invoices"):
        invoice_service.reject_invoice(w.db, getattr(w, role), inv, reason="x")
