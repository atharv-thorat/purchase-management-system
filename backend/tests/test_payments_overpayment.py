"""Rule 12: payments on MATCHED / PARTIALLY_PAID invoices, partial allowed, no overpayment."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import InvoiceStatus
from app.services import payment_service
from tests.conftest import LAPTOP

D = Decimal


def _matched(w):
    po = w.po()
    w.receive(po)
    return w.invoice(po)  # ₹10,000


def _pay(w, inv, amount, actor=None, mode="NEFT", reference_no="UTR1", paid_on=None):
    return payment_service.record_payment(w.db, actor or w.accounts, inv, amount=amount, mode=mode,
                                          reference_no=reference_no, paid_on=paid_on or clock.today())


def test_partial_then_final_payment(w):
    inv = _matched(w)
    _pay(w, inv, "4000")
    assert inv.status is InvoiceStatus.PARTIALLY_PAID
    assert payment_service.balance_due(inv) == D("6000.00")
    _pay(w, inv, "6000", mode="CHEQUE", reference_no="CHQ 004512")
    assert inv.status is InvoiceStatus.PAID
    assert payment_service.amount_paid(inv) == D("10000.00")
    assert [a for a, _, _ in w.audit(inv)][-2:] == ["PAYMENT_RECORDED", "PAYMENT_RECORDED"]
    assert w.audit(inv)[-1] == ("PAYMENT_RECORDED", "PARTIALLY_PAID", "PAID")


def test_full_payment_in_one_go(w):
    inv = _matched(w)
    _pay(w, inv, "10000", mode="UPI", reference_no="upi-8812")
    assert inv.status is InvoiceStatus.PAID


def test_overpayment_is_blocked(w):
    inv = _matched(w)
    with pytest.raises(BusinessRuleViolation) as exc:
        _pay(w, inv, "10000.01")
    assert exc.value.message == ("Payment of ₹10,000.01 exceeds the balance due of ₹10,000.00 on invoice INV-001")
    assert inv.payments == [] and inv.status is InvoiceStatus.MATCHED


def test_overpaying_the_remaining_balance_is_blocked(w):
    inv = _matched(w)
    _pay(w, inv, "7500")
    with pytest.raises(BusinessRuleViolation, match="exceeds the balance due of ₹2,500.00"):
        _pay(w, inv, "3000")
    assert len(inv.payments) == 1
    _pay(w, inv, "2500")  # the session is still usable and the right amount goes through
    assert inv.status is InvoiceStatus.PAID


@pytest.mark.parametrize("amount, message", [
    ("0", "must be greater than 0"), ("-5", "must be greater than 0"),
    ("10.001", "at most 2 decimal places"), (100.5, "not float"),
])
def test_amount_validation(w, amount, message):
    with pytest.raises(BusinessRuleViolation, match=message):
        _pay(w, _matched(w), amount)


def test_mode_reference_and_date_validation(w):
    inv = _matched(w)
    with pytest.raises(BusinessRuleViolation, match="Payment mode must be one of NEFT, CHEQUE, UPI"):
        _pay(w, inv, "1", mode="CASH")
    with pytest.raises(BusinessRuleViolation, match="Payment reference number is required"):
        _pay(w, inv, "1", reference_no=" ")
    with pytest.raises(BusinessRuleViolation, match="cannot be in the future"):
        _pay(w, inv, "1", paid_on=clock.today() + timedelta(days=1))
    with pytest.raises(BusinessRuleViolation, match="is before the invoice date"):
        _pay(w, inv, "1", paid_on=clock.today() - timedelta(days=1))


def test_no_payment_on_mismatched_invoice(w):
    po = w.po()
    w.receive(po, accept={LAPTOP: "5"})
    inv = w.invoice(po, lines={LAPTOP: ("10", "1000")})
    with pytest.raises(InvalidTransition, match="Cannot record a payment against invoice INV-001: it is MISMATCH"):
        _pay(w, inv, "1")


def test_no_payment_on_a_paid_invoice(w):
    inv = _matched(w)
    _pay(w, inv, "10000")
    with pytest.raises(InvalidTransition, match="it is PAID"):
        _pay(w, inv, "1")


@pytest.mark.parametrize("role", ["requester", "head", "finance", "purchase", "store", "admin"])
def test_only_accounts_records_payments(w, role):
    inv = _matched(w)
    with pytest.raises(Forbidden, match="Only ACCOUNTS users can record payments"):
        _pay(w, inv, "1", actor=getattr(w, role))
