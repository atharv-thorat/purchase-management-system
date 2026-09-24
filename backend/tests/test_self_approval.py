"""Rule 2: nobody can approve (or reject) their own request."""

import pytest

from app.core.errors import Forbidden
from app.models.enums import PRStatus, Role
from app.services import master_service, pr_service


def test_dept_head_cannot_approve_own_pr(w):
    pr = w.submitted(requester=w.head)
    with pytest.raises(Forbidden, match="You cannot approve your own purchase request"):
        pr_service.approve_pr(w.db, w.head, pr)
    assert pr.status is PRStatus.PENDING_FINANCE
    assert pr.approval_logs == []


def test_dept_head_cannot_reject_own_pr(w):
    pr = w.submitted(requester=w.head)
    with pytest.raises(Forbidden, match="You cannot reject your own purchase request"):
        pr_service.reject_pr(w.db, w.head, pr, comment="changed my mind")


def test_self_approval_is_blocked_even_after_a_role_change(w):
    """A requester promoted to dept head while their PR waits still can't approve it."""
    pr = w.submitted()
    master_service.update_user(w.db, w.admin, w.requester, role=Role.DEPT_HEAD)
    with pytest.raises(Forbidden, match="your own purchase request"):
        pr_service.approve_pr(w.db, w.requester, pr)
    pr_service.approve_pr(w.db, w.head, pr)  # the other IT head still can
    assert pr.status is PRStatus.APPROVED
