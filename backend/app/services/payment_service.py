"""Payments (rule 12): partial payments, no overpayment, invoice status, PO auto-close."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models.enums import AuditAction, InvoiceStatus, PaymentMode, Role
from app.models.invoice import Invoice, Payment
from app.models.master import User
from app.services import state_machine as sm
from app.services._common import ensure_role, fmt_date, inr, money, not_in_future, require_text
from app.services.po_service import try_auto_close


def amount_paid(invoice: Invoice) -> Decimal:
    return sum((p.amount for p in invoice.payments), Decimal("0"))


def balance_due(invoice: Invoice) -> Decimal:
    return invoice.total - amount_paid(invoice)


@atomic
def record_payment(db: Session, actor: User, invoice: Invoice, *, amount, mode: PaymentMode | str,
                   reference_no: str, paid_on: date) -> Payment:
    ensure_role(actor, Role.ACCOUNTS, to="record payments")
    sm.check(invoice, AuditAction.PAYMENT_RECORDED)  # MATCHED / PARTIALLY_PAID only
    amount = money(amount, "Payment amount")
    try:
        mode = PaymentMode(mode)
    except ValueError:
        raise BusinessRuleViolation(f"Payment mode must be one of {', '.join(m.value for m in PaymentMode)}") from None
    reference_no = require_text(reference_no, "Payment reference number")
    not_in_future(paid_on, "Payment date")
    if paid_on < invoice.invoice_date:
        raise BusinessRuleViolation(f"Payment date {fmt_date(paid_on)} is before the invoice date "
                                    f"{fmt_date(invoice.invoice_date)}")
    balance = balance_due(invoice)
    if amount > balance:
        raise BusinessRuleViolation(
            f"Payment of {inr(amount)} exceeds the balance due of {inr(balance)} on invoice "
            f"{invoice.supplier_invoice_number}"
        )

    payment = Payment(invoice=invoice, amount=amount, mode=mode, reference_no=reference_no, paid_on=paid_on,
                      recorded_by=actor.id)
    db.add(payment)
    remaining = balance - amount
    target = InvoiceStatus.PAID if remaining == 0 else InvoiceStatus.PARTIALLY_PAID
    sm.transition(db, invoice, AuditAction.PAYMENT_RECORDED, target, actor,
                  {"amount": str(amount), "mode": mode.value, "reference_no": reference_no, "balance": str(remaining)})
    try_auto_close(db, invoice.po, actor, trigger="payment")
    return payment
