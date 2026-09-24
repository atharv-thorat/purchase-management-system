"""The demo seed is built through the services and must pass verify.py (D-41, D-49)."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.core import clock
from app.models import Invoice, POLine, PurchaseOrder, PurchaseRequest
from app.seed.seed import seed
from app.seed.verify import verify
from app.services import payment_service, pr_service


SEEDED_AT = datetime(2026, 9, 24, 18, 0)


@pytest.fixture
def demo(db, password_hash):
    clock.freeze(SEEDED_AT)  # the demo happens right after seeding
    return seed(db, password_hash=password_hash, now=SEEDED_AT)


def _statuses(db, model, number_attr):
    return {getattr(r, number_attr): r.status for r in db.scalars(select(model))}


def test_seed_produces_every_demo_state(db, demo):
    assert _statuses(db, PurchaseRequest, "pr_number") == {
        "PR-0001": "PO_CREATED", "PR-0002": "PO_CREATED", "PR-0003": "PO_CREATED", "PR-0004": "REJECTED",
        "PR-0005": "APPROVED", "PR-0006": "PENDING_FINANCE", "PR-0007": "PENDING_DEPT_HEAD", "PR-0008": "DRAFT",
    }
    assert _statuses(db, PurchaseOrder, "po_number") == {
        "PO-0001": "CLOSED", "PO-0002": "SHORT_CLOSED", "PO-0003": "PARTIALLY_RECEIVED"}
    assert [(i.supplier_invoice_number, i.status) for i in db.scalars(select(Invoice).order_by(Invoice.id))] == [
        ("INF/2026/0412", "PAID"), ("TSPL/2026/1187", "REJECTED"), ("TSPL/2026/1187", "PARTIALLY_PAID"),
        ("SSST/26-27/0923", "MISMATCH")]
    pr5 = db.scalar(select(PurchaseRequest).where(PurchaseRequest.pr_number == "PR-0005"))
    assert len(pr5.quotations) == 3
    assert verify(db) == []


def test_mismatch_reason_comes_from_the_real_match(db, demo):
    inv = db.scalar(select(Invoice).where(Invoice.status == "MISMATCH"))
    assert inv.mismatch_details == "MS Steel Rod 12 mm: invoiced 300, accepted 280"


def test_pending_ops_pr_shows_the_over_budget_warning(db, demo):
    pr7 = db.scalar(select(PurchaseRequest).where(PurchaseRequest.pr_number == "PR-0007"))
    check = pr_service.budget_check(db, pr7)
    assert (check.approved_this_month, check.projected, check.over_budget) == (55000, 504000, True)


def test_paying_the_short_closed_balance_closes_po_0002(db, demo):
    po2 = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-0002"))
    live = next(i for i in po2.invoices if i.status == "PARTIALLY_PAID")
    assert payment_service.balance_due(live) == 38000
    payment_service.record_payment(db, demo.u("accounts"), live, amount="38000", mode="NEFT",
                                   reference_no="UTR-DEMO", paid_on=clock.today())
    assert po2.status == "CLOSED"


@pytest.mark.parametrize("now", [datetime(2026, 10, 1, 0, 30), datetime(2026, 10, 3, 9, 0),
                                 datetime(2026, 10, 31, 23, 0)])
def test_seed_timeline_stays_inside_the_current_month(db, password_hash, now):
    seed(db, password_hash=password_hash, now=now)
    month_start = now.replace(day=1, hour=0, minute=0)
    stamps = [pr.created_at for pr in db.scalars(select(PurchaseRequest))]
    assert all(month_start <= t <= now for t in stamps)
    assert verify(db) == []


def test_verify_catches_tampering(db, demo):
    line = db.scalar(select(POLine).where(POLine.qty_accepted > 0))
    line.qty_accepted -= 1
    pr6 = db.scalar(select(PurchaseRequest).where(PurchaseRequest.pr_number == "PR-0006"))
    pr6.status = "APPROVED"
    problems = verify(db)
    assert any("qty_accepted" in p for p in problems)
    assert any("PR-0006: approved without final_approved_at" in p for p in problems)
    assert any("last audit row says PENDING_FINANCE" in p for p in problems)
