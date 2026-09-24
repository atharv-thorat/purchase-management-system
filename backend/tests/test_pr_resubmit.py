"""Rule 3: rejection needs a comment; edit and resubmit restarts the whole chain (D-02)."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden
from app.models.enums import ApprovalAction, ApprovalLevel, PRStatus
from app.services import pr_service
from tests.conftest import LARGE, SMALL


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_rejection_requires_a_comment(w, comment):
    pr = w.submitted()
    with pytest.raises(BusinessRuleViolation, match="A comment explaining the rejection is required"):
        pr_service.reject_pr(w.db, w.head, pr, comment=comment)
    assert pr.status is PRStatus.PENDING_DEPT_HEAD


def test_rejection_is_logged_with_its_comment(w):
    pr = w.submitted()
    pr_service.reject_pr(w.db, w.head, pr, comment="Too expensive")
    assert pr.status is PRStatus.REJECTED
    assert pr.rejection_reason == "Too expensive"
    [log] = pr.approval_logs
    assert (log.level, log.action, log.comment) == (ApprovalLevel.DEPT_HEAD, ApprovalAction.REJECTED, "Too expensive")
    assert w.audit(pr)[-1] == ("REJECTED", "PENDING_DEPT_HEAD", "REJECTED")


def test_finance_rejection_then_resubmit_restarts_at_the_dept_head(w):
    pr = w.submitted(lines=LARGE)
    pr_service.approve_pr(w.db, w.head, pr)
    pr_service.reject_pr(w.db, w.finance, pr, comment="Get a cheaper model")
    pr_service.update_pr(w.db, w.requester, pr, justification="Cheaper model", required_by=pr.required_by,
                         lines=w.pr_lines(LARGE))
    pr_service.submit_pr(w.db, w.requester, pr)
    assert pr.status is PRStatus.PENDING_DEPT_HEAD  # not PENDING_FINANCE: the DH approves again
    assert pr.rejection_reason is None
    assert w.audit(pr)[-2:] == [("EDITED", "REJECTED", "REJECTED"), ("RESUBMITTED", "REJECTED", "PENDING_DEPT_HEAD")]
    pr_service.approve_pr(w.db, w.head, pr)
    pr_service.approve_pr(w.db, w.finance, pr)
    assert pr.status is PRStatus.APPROVED
    assert len(pr.approval_logs) == 4  # history kept


def test_rejected_pr_can_be_resubmitted_without_edits(w):
    pr = w.submitted()
    pr_service.reject_pr(w.db, w.head, pr, comment="Explain more")
    pr_service.submit_pr(w.db, w.requester, pr)
    assert pr.status is PRStatus.PENDING_DEPT_HEAD


def test_dept_head_pr_resubmits_to_finance(w):
    pr = w.submitted(requester=w.head, lines=SMALL)
    pr_service.reject_pr(w.db, w.finance, pr, comment="Not this quarter")
    pr_service.submit_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.PENDING_FINANCE


def test_only_the_owner_can_resubmit(w):
    pr = w.submitted()
    pr_service.reject_pr(w.db, w.head, pr, comment="No")
    with pytest.raises(Forbidden):
        pr_service.submit_pr(w.db, w.head, pr)
