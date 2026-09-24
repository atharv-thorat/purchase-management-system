"""Rule 14 / D-34: PO closes itself once all accepted qty is invoiced and every live invoice is PAID."""

import pytest
from sqlalchemy import select

from app.core.errors import InvalidTransition
from app.models import AuditLog
from app.models.enums import InvoiceStatus, POStatus
from app.services import invoice_service, po_service
from tests.conftest import LAPTOP, MOUSE, TWO_LINES


def test_final_payment_closes_a_fully_received_po(w):
    po = w.po(lines=TWO_LINES)
    w.receive(po)
    inv = w.invoice(po)
    w.pay(inv, "5000")
    assert po.status is POStatus.FULLY_RECEIVED
    w.pay(inv)
    assert po.status is POStatus.CLOSED
    assert w.audit(po)[-1] == ("CLOSED", "FULLY_RECEIVED", "CLOSED")


def test_split_invoices_close_the_po_only_when_the_last_is_paid(w):
    po = w.po(lines=TWO_LINES)
    w.receive(po)
    laptops = w.invoice(po, "INV-1", lines={LAPTOP: ("10", "1000")})
    w.pay(laptops)
    assert po.status is POStatus.FULLY_RECEIVED  # mice not invoiced yet
    mice = w.invoice(po, "INV-2", lines={MOUSE: ("20", "100")})
    w.pay(mice)
    assert po.status is POStatus.CLOSED


def test_open_mismatch_invoice_blocks_closure_until_rejected(w):
    po = w.po()
    w.receive(po)
    stray = w.invoice(po, "INV-X", lines={LAPTOP: ("10", "999")})  # MISMATCH
    w.pay(w.invoice(po, "INV-1"))
    assert po.status is POStatus.FULLY_RECEIVED  # the MISMATCH invoice is still live
    invoice_service.reject_invoice(w.db, w.accounts, stray, reason="Duplicate bill at the wrong price")
    assert po.status is POStatus.CLOSED
    closed = w.db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert (closed.action, closed.details) == ("CLOSED", {"auto": True, "trigger": "invoice rejected"})


def test_partially_received_po_does_not_close_even_if_settled(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "4"})
    w.pay(w.invoice(po))
    assert po.status is POStatus.PARTIALLY_RECEIVED


def test_short_closed_po_closes_when_accepted_goods_are_paid(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "4"})
    po_service.short_close_po(w.db, w.purchase, po, reason="Rest not needed")
    inv = w.invoice(po)
    assert po.status is POStatus.SHORT_CLOSED
    w.pay(inv)
    assert po.status is POStatus.CLOSED
    assert w.audit(po)[-1] == ("CLOSED", "SHORT_CLOSED", "CLOSED")


def test_rejected_invoices_are_ignored_by_the_close_condition(w):
    po = w.po()
    w.receive(po)
    bad = w.invoice(po, "INV-1", lines={LAPTOP: ("10", "1")})
    invoice_service.reject_invoice(w.db, w.accounts, bad, reason="Wrong price")
    assert po.status is POStatus.FULLY_RECEIVED  # nothing invoiced yet
    w.pay(w.invoice(po, "INV-2"))
    assert po.status is POStatus.CLOSED
    assert [i.status for i in po.invoices] == [InvoiceStatus.REJECTED, InvoiceStatus.PAID]


def test_closed_po_accepts_nothing_more(w):
    po = w.po()
    w.receive(po)
    w.pay(w.invoice(po))
    assert po_service.close_condition_met(po)
    with pytest.raises(InvalidTransition):
        w.receive(po, accept={LAPTOP: "1"})
    with pytest.raises(InvalidTransition):
        w.invoice(po, "INV-2", lines={LAPTOP: ("1", "1000")})
