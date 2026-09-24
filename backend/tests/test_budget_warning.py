"""Rule 4 / D-05 / D-36: the over-budget warning — shown, never blocking, logged as seen."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.core import clock
from app.models import AuditLog
from app.models.enums import PRStatus
from app.services import master_service, po_service, pr_service
from tests.conftest import LAPTOP, SMALL

D = Decimal


def lines(amount: int):
    return ((LAPTOP, "1", str(amount)),)


def _ops_budget(w, amount: str):
    ops = w.requester_ops.department
    master_service.update_department(w.db, w.admin, ops, monthly_budget=amount)
    return ops


def test_under_budget_is_not_flagged(w):
    pr = w.submitted(lines=lines(10_000))
    check = pr_service.budget_check(w.db, pr)
    assert (check.department, check.monthly_budget, check.approved_this_month, check.projected, check.over_budget) == \
        ("IT", D("1000000.00"), D("0"), D("10000.00"), False)
    pr_service.approve_pr(w.db, w.head, pr)
    assert pr.approval_logs[-1].over_budget is False


def test_over_budget_can_still_be_approved_and_the_warning_is_logged(w):
    _ops_budget(w, "30000")
    w.approved(requester=w.requester_ops, lines=lines(20_000))
    pr = w.submitted(requester=w.requester_ops, lines=lines(15_000))
    check = pr_service.budget_check(w.db, pr)
    assert (check.approved_this_month, check.projected, check.over_budget) == (D("20000.00"), D("35000.00"), True)
    assert check.remaining_after == D("-5000.00")
    pr_service.approve_pr(w.db, w.head_ops, pr)
    assert pr.status is PRStatus.APPROVED
    assert pr.approval_logs[-1].over_budget is True
    last = w.db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert last.details["over_budget"] is True
    assert last.details["budget_note"] == "₹35,000.00 projected against ₹30,000.00 Operations budget"


def test_exactly_on_budget_is_not_over(w):
    _ops_budget(w, "30000")
    w.approved(requester=w.requester_ops, lines=lines(20_000))
    pr = w.submitted(requester=w.requester_ops, lines=lines(10_000))
    assert pr_service.budget_check(w.db, pr).over_budget is False


def test_rejection_also_records_the_warning_the_approver_saw(w):
    _ops_budget(w, "5000")
    pr = w.submitted(requester=w.requester_ops, lines=lines(10_000))
    pr_service.reject_pr(w.db, w.head_ops, pr, comment="Over budget")
    assert pr.approval_logs[-1].over_budget is True


def test_committed_uses_the_po_total_once_a_po_exists(w):
    po = w.po(requester=w.requester_ops, lines=lines(20_000), prices={LAPTOP: "12000"})
    assert pr_service.committed_this_month(w.db, po.pr.department_id) == D("12000.00")


def test_cancelled_po_falls_back_to_the_estimate(w):
    po = w.po(requester=w.requester_ops, lines=lines(20_000), prices={LAPTOP: "12000"})
    po_service.cancel_po(w.db, w.purchase, po, reason="Supplier backed out")
    assert po.pr.status is PRStatus.APPROVED
    assert pr_service.committed_this_month(w.db, po.pr.department_id) == D("20000.00")


def test_only_approved_and_po_created_prs_of_this_department_this_month_count(w):
    ops = w.requester_ops.department
    w.approved(requester=w.requester_ops, lines=lines(1_000))  # counts
    w.po(requester=w.requester_ops, lines=lines(2_000))  # PO_CREATED, counts at PO total
    w.submitted(requester=w.requester_ops, lines=lines(40_000))  # pending: no
    w.draft(requester=w.requester_ops, lines=lines(80_000))  # draft: no
    rejected = w.submitted(requester=w.requester_ops, lines=lines(160_000))
    pr_service.reject_pr(w.db, w.head_ops, rejected, comment="no")  # rejected: no
    w.approved(requester=w.requester, lines=lines(320_000))  # other department: no
    assert pr_service.committed_this_month(w.db, ops.id) == D("3000.00")


def test_previous_months_approvals_do_not_count(w):
    ops = w.requester_ops.department
    clock.freeze(datetime(2026, 8, 31, 23, 59))
    w.approved(requester=w.requester_ops, lines=lines(9_000))
    clock.freeze(datetime(2026, 9, 1, 0, 0))
    w.approved(requester=w.requester_ops, lines=lines(1_000))
    assert pr_service.committed_this_month(w.db, ops.id) == D("1000.00")
    clock.freeze(datetime(2026, 10, 1, 9, 0))
    assert pr_service.committed_this_month(w.db, ops.id) == D("0")


def test_month_is_the_final_approval_month_not_the_submit_month(w):
    ops = w.requester_ops.department
    clock.freeze(datetime(2026, 8, 30, 12, 0))
    pr = w.submitted(requester=w.requester_ops, lines=((LAPTOP, "1", "60000"),))
    pr_service.approve_pr(w.db, w.head_ops, pr)  # dept head in August
    clock.freeze(datetime(2026, 9, 2, 12, 0))
    pr_service.approve_pr(w.db, w.finance, pr)  # final approval in September
    assert pr_service.committed_this_month(w.db, ops.id) == D("60000.00")


def test_the_pr_being_approved_is_excluded_from_the_committed_sum(w):
    pr = w.approved(lines=SMALL)
    check = pr_service.budget_check(w.db, pr)
    assert check.approved_this_month == D("0")
    assert check.projected == pr.estimated_total
