"""Rule 1 (threshold routing, D-12), rule 2 (who may act) and D-01 (dept-head PRs go to FINANCE)."""

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models.enums import ApprovalAction, ApprovalLevel, PRStatus
from app.services import master_service, pr_service
from tests.conftest import LAPTOP, LARGE, SMALL

AT_THRESHOLD = ((LAPTOP, "10", "5000"),)  # exactly ₹50,000


def test_at_or_below_threshold_dept_head_approval_is_final(w):
    pr = w.submitted(lines=AT_THRESHOLD)
    pr_service.approve_pr(w.db, w.head, pr, comment="Fine")
    assert pr.status is PRStatus.APPROVED
    assert pr.final_approved_at == clock.now()
    [log] = pr.approval_logs
    assert (log.level, log.action, log.approver, log.comment) == \
        (ApprovalLevel.DEPT_HEAD, ApprovalAction.APPROVED, w.head, "Fine")
    assert w.audit(pr)[-1] == ("APPROVED", "PENDING_DEPT_HEAD", "APPROVED")


def test_above_threshold_goes_to_finance_after_the_dept_head(w):
    pr = w.submitted(lines=LARGE)
    pr_service.approve_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.PENDING_FINANCE
    assert pr.final_approved_at is None
    pr_service.approve_pr(w.db, w.finance, pr)
    assert pr.status is PRStatus.APPROVED
    assert [log.level for log in pr.approval_logs] == [ApprovalLevel.DEPT_HEAD, ApprovalLevel.FINANCE]
    assert [a for a, _, _ in w.audit(pr)] == ["CREATED", "SUBMITTED", "APPROVED", "APPROVED"]


def test_threshold_is_read_when_the_dept_head_approves_not_at_submit(w):
    pr = w.submitted(lines=LARGE)  # ₹60,000 > ₹50,000 at submit time
    master_service.set_setting(w.db, w.admin, "FINANCE_APPROVAL_THRESHOLD", "100000")
    pr_service.approve_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.APPROVED


def test_lowering_the_threshold_routes_small_prs_to_finance(w):
    master_service.set_setting(w.db, w.admin, "FINANCE_APPROVAL_THRESHOLD", "5000")
    pr = w.submitted(lines=SMALL)  # ₹10,000
    pr_service.approve_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.PENDING_FINANCE


@pytest.mark.parametrize("value, message", [("abc", "must be a number"), ("-1", "cannot be negative"),
                                            ("1.005", "at most 2 decimal places")])
def test_threshold_setting_is_validated(w, value, message):
    with pytest.raises(BusinessRuleViolation, match=message):
        master_service.set_setting(w.db, w.admin, "FINANCE_APPROVAL_THRESHOLD", value)


# ---- D-01: PRs raised by a dept head -------------------------------------------------------------


def test_dept_head_pr_goes_straight_to_finance_whatever_the_amount(w):
    pr = w.submitted(requester=w.head, lines=SMALL)
    assert pr.status is PRStatus.PENDING_FINANCE
    pr_service.approve_pr(w.db, w.finance, pr)
    assert pr.status is PRStatus.APPROVED
    assert [log.level for log in pr.approval_logs] == [ApprovalLevel.FINANCE]


def test_other_departments_head_cannot_approve_a_dept_heads_pr(w):
    pr = w.submitted(requester=w.head, lines=SMALL)
    with pytest.raises(Forbidden, match="waiting for Finance"):
        pr_service.approve_pr(w.db, w.head_ops, pr)


# ---- rule 2: who may act -------------------------------------------------------------------------


def test_head_of_another_department_cannot_approve(w):
    pr = w.submitted()
    with pytest.raises(Forbidden, match=f"{pr.pr_number} is waiting for the IT department head"):
        pr_service.approve_pr(w.db, w.head_ops, pr)
    with pytest.raises(Forbidden, match="IT department head"):
        pr_service.reject_pr(w.db, w.head_ops, pr, comment="no")


def test_finance_cannot_skip_the_dept_head(w):
    pr = w.submitted(lines=LARGE)
    with pytest.raises(Forbidden, match="waiting for the IT department head"):
        pr_service.approve_pr(w.db, w.finance, pr)


def test_dept_head_cannot_act_at_the_finance_level(w):
    pr = w.submitted(lines=LARGE)
    pr_service.approve_pr(w.db, w.head, pr)
    with pytest.raises(Forbidden, match="waiting for Finance"):
        pr_service.approve_pr(w.db, w.head, pr)


@pytest.mark.parametrize("role", ["requester", "purchase", "store", "accounts", "admin"])
def test_non_approver_roles_cannot_approve_or_reject(w, role):
    pr = w.submitted()
    with pytest.raises(Forbidden, match="Only DEPT_HEAD or FINANCE users can approve"):
        pr_service.approve_pr(w.db, w.users[role] if role != "requester" else w.requester_ops, pr)
    with pytest.raises(Forbidden, match="Only DEPT_HEAD or FINANCE users can reject"):
        pr_service.reject_pr(w.db, w.users[role] if role != "requester" else w.requester_ops, pr, comment="x")


@pytest.mark.parametrize("state", ["draft", "approved"])
def test_approving_a_pr_that_is_not_pending_is_an_invalid_transition(w, state):
    pr = getattr(w, state)()
    with pytest.raises(InvalidTransition, match=f"Cannot approve .* it is {pr.status}"):
        pr_service.approve_pr(w.db, w.head, pr)


def test_approval_inbox(w):
    it_pending = w.submitted()
    ops_pending = w.submitted(requester=w.requester_ops)
    big = w.submitted(lines=LARGE)
    pr_service.approve_pr(w.db, w.head, big)
    own = w.submitted(requester=w.head)
    assert pr_service.pending_approvals(w.db, w.head) == [it_pending]
    assert pr_service.pending_approvals(w.db, w.head_ops) == [ops_pending]
    assert pr_service.pending_approvals(w.db, w.finance) == [big, own]
    assert pr_service.pending_approvals(w.db, w.purchase) == []
