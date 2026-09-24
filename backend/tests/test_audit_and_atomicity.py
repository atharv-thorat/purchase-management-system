"""Rule 15 (every status change audited, D-28) and one-transaction-per-action (D-46)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation
from app.models import AuditLog, Invoice, PurchaseOrder, PurchaseRequest
from app.models.enums import AuditAction, DocumentType, InvoiceStatus, PRStatus
from app.seed.verify import verify
from app.services import invoice_service, po_service, pr_service, quotation_service, state_machine
from app.services.numbering import next_number
from tests.conftest import LAPTOP, LARGE, TWO_LINES


def _full_cycle(w):
    pr = w.submitted(lines=LARGE)
    pr_service.reject_pr(w.db, w.head, pr, comment="Cheaper please")
    pr_service.submit_pr(w.db, w.requester, pr)
    pr_service.approve_pr(w.db, w.head, pr)
    pr_service.approve_pr(w.db, w.finance, pr)
    q = w.quote(pr)
    po = quotation_service.select_quotation(w.db, w.purchase, pr, q, single_quote_justification="Sole")
    w.receive(po, accept={LAPTOP: "6"})
    bad = w.invoice(po, "B-1", lines={LAPTOP: ("10", "6000")})
    invoice_service.reject_invoice(w.db, w.accounts, bad, reason="Too many")
    po_service.short_close_po(w.db, w.purchase, po, reason="Enough")
    good = w.invoice(po, "B-1")
    w.pay(good, "1000")
    w.pay(good)
    return pr, po, bad, good


def test_every_status_change_has_exactly_one_audit_row_with_actor(w):
    pr, po, bad, good = _full_cycle(w)
    assert [a for a, _, _ in w.audit(pr)] == ["CREATED", "SUBMITTED", "REJECTED", "RESUBMITTED", "APPROVED",
                                              "APPROVED", "PO_CREATED"]
    assert w.audit(po) == [("ISSUED", None, "ISSUED"), ("GRN_RECORDED", "ISSUED", "PARTIALLY_RECEIVED"),
                           ("SHORT_CLOSED", "PARTIALLY_RECEIVED", "SHORT_CLOSED"), ("CLOSED", "SHORT_CLOSED", "CLOSED")]
    assert [a for a, _, _ in w.audit(bad)] == ["ENTERED", "MISMATCHED", "REJECTED"]
    assert [a for a, _, _ in w.audit(good)] == ["ENTERED", "MATCHED", "PAYMENT_RECORDED", "PAYMENT_RECORDED"]
    assert w.db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id.is_(None))) == 0
    assert verify(w.db) == []


def test_the_whole_database_stays_consistent_after_a_mixed_workload(w):
    _full_cycle(w)
    cancelled = w.po()
    po_service.cancel_po(w.db, w.purchase, cancelled, reason="Duplicate")
    w.po(lines=TWO_LINES)
    partly = w.po()
    w.receive(partly, accept={LAPTOP: "3"})
    w.invoice(partly, "P-1", lines={LAPTOP: ("5", "1000")})  # MISMATCH left open
    assert verify(w.db) == []


def test_a_rejected_action_leaves_no_trace(w):
    po = w.po()
    w.receive(po)
    inv = w.invoice(po)
    audit_before = w.db.scalar(select(func.count()).select_from(AuditLog))
    with pytest.raises(BusinessRuleViolation):
        w.pay(inv, "99999")
    assert w.db.scalar(select(func.count()).select_from(AuditLog)) == audit_before
    assert inv.payments == [] and inv.status is InvoiceStatus.MATCHED


def test_atomic_rolls_back_changes_made_before_the_failure(w):
    """An action that has already changed a status, written audit and taken a number, then
    fails, leaves none of it behind — and the session carries on (D-46)."""
    pr = w.submitted()

    @atomic
    def half_done(db, pr):
        state_machine.transition(db, pr, AuditAction.APPROVED, PRStatus.APPROVED, w.head)
        next_number(db, DocumentType.PO)
        raise BusinessRuleViolation("failed late")

    audit_before = w.db.scalar(select(func.count()).select_from(AuditLog))
    with pytest.raises(BusinessRuleViolation, match="failed late"):
        half_done(w.db, pr)
    assert pr.status is PRStatus.PENDING_DEPT_HEAD
    assert w.db.scalar(select(func.count()).select_from(AuditLog)) == audit_before
    assert next_number(w.db, DocumentType.PO) == "PO-0001"
    pr_service.approve_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.APPROVED


def test_committed_work_survives_a_new_session(w, engine):
    pr = w.approved()
    w.db.commit()
    with Session(engine) as other:
        assert other.get(PurchaseRequest, pr.id).status is PRStatus.APPROVED
        assert other.scalar(select(func.count()).select_from(PurchaseOrder)) == 0
        assert other.scalar(select(func.count()).select_from(Invoice)) == 0
