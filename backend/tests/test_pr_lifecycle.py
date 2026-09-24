"""Creating, editing, deleting and submitting PRs (D-13, D-19, D-29 and input rules D-48)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models import PurchaseRequest
from app.models.enums import PRStatus
from app.services import pr_service
from app.services.pr_service import PRLineIn
from tests.conftest import LAPTOP, MOUSE, SMALL, TWO_LINES


def _create(w, actor=None, lines=None, justification="Needed", required_by=None):
    lines = w.pr_lines(TWO_LINES) if lines is None else lines
    return pr_service.create_pr(w.db, actor or w.requester, justification=justification,
                                required_by=required_by or clock.today() + timedelta(days=10), lines=lines)


def test_create_makes_a_numbered_draft_with_a_computed_total(w):
    pr = _create(w)
    assert pr.pr_number == "PR-0001"
    assert pr.status is PRStatus.DRAFT
    assert pr.estimated_total == Decimal("12000.00")  # 10 × 1000 + 20 × 100
    assert pr.department.name == "IT"
    assert w.audit(pr) == [("CREATED", None, "DRAFT")]


def test_dept_head_can_raise_a_pr(w):
    assert _create(w, actor=w.head).requester is w.head


@pytest.mark.parametrize("role", ["finance", "purchase", "store", "accounts", "admin"])
def test_roles_without_a_department_cannot_raise_prs(w, role):
    with pytest.raises(Forbidden, match="Only REQUESTER or DEPT_HEAD users can raise purchase requests"):
        _create(w, actor=w.users[role])


def test_deactivated_requester_cannot_raise_prs(w):
    w.requester.is_active = False
    with pytest.raises(Forbidden, match="deactivated"):
        _create(w)


@pytest.mark.parametrize("lines, message", [
    ("empty", "needs at least one line"),
    ("unknown_item", "Line 1: item 9999 does not exist"),
    ("dup", "appears more than once; combine it into one line"),
    ("zero_qty", "quantity must be greater than 0"),
    ("negative_price", "estimated unit price must be greater than 0"),
    ("float_qty", "must be a decimal number, not float"),
    ("too_precise", "can have at most 3 decimal places"),
    ("not_a_number", "must be a number"),
])
def test_line_validation(w, lines, message):
    laptop = w.items[LAPTOP].id
    lines = {
        "empty": [],
        "unknown_item": [PRLineIn(9999, 1, 1)],
        "dup": [PRLineIn(laptop, 1, 10), PRLineIn(laptop, 2, 10)],
        "zero_qty": [PRLineIn(laptop, 0, 10)],
        "negative_price": [PRLineIn(laptop, 1, -5)],
        "float_qty": [PRLineIn(laptop, 1.5, 10)],
        "too_precise": [PRLineIn(laptop, "1.0005", 10)],
        "not_a_number": [PRLineIn(laptop, "lots", 10)],
    }[lines]
    with pytest.raises(BusinessRuleViolation, match=message):
        _create(w, lines=lines)


def test_every_line_problem_is_reported_at_once(w):
    lines = [PRLineIn(w.items[LAPTOP].id, 0, 10), PRLineIn(w.items[MOUSE].id, 1, 0)]
    with pytest.raises(BusinessRuleViolation) as exc:
        _create(w, lines=lines)
    assert len(exc.value.details) == 2
    assert "Line 1 (Laptop" in exc.value.message and "Line 2 (Wireless Mouse)" in exc.value.message


def test_justification_is_required(w):
    with pytest.raises(BusinessRuleViolation, match="Justification is required"):
        _create(w, justification="   ")


def test_required_by_cannot_be_in_the_past(w):
    with pytest.raises(BusinessRuleViolation, match="is in the past"):
        _create(w, required_by=clock.today() - timedelta(days=1))


# ---- edit ---------------------------------------------------------------------------------------


def test_owner_edits_a_draft_and_the_total_is_recomputed(w):
    pr = _create(w)
    pr_service.update_pr(w.db, w.requester, pr, justification="Changed", required_by=pr.required_by,
                         lines=w.pr_lines(SMALL))
    assert (pr.justification, len(pr.lines), pr.estimated_total) == ("Changed", 1, Decimal("10000.00"))
    assert w.audit(pr)[-1] == ("EDITED", "DRAFT", "DRAFT")


def test_only_the_owner_can_edit(w):
    pr = _create(w)
    with pytest.raises(Forbidden, match=f"Only the requester of {pr.pr_number} can edit it"):
        pr_service.update_pr(w.db, w.head, pr, justification="x", required_by=pr.required_by,
                             lines=w.pr_lines(SMALL))


@pytest.mark.parametrize("state", ["submitted", "approved"])
def test_submitted_or_approved_prs_cannot_be_edited(w, state):
    pr = getattr(w, state)()
    with pytest.raises(InvalidTransition, match=f"Cannot edit .* it is {pr.status}"):
        pr_service.update_pr(w.db, w.requester, pr, justification="x", required_by=pr.required_by,
                             lines=w.pr_lines(SMALL))


def test_failed_edit_leaves_the_pr_untouched(w):
    pr = _create(w)
    with pytest.raises(BusinessRuleViolation):
        pr_service.update_pr(w.db, w.requester, pr, justification="x", required_by=pr.required_by,
                             lines=[PRLineIn(w.items[LAPTOP].id, 0, 1)])
    assert len(pr.lines) == 2 and pr.estimated_total == Decimal("12000.00")


# ---- delete -------------------------------------------------------------------------------------


def test_owner_deletes_a_draft(w):
    pr = _create(w)
    pr_id = pr.id
    pr_service.delete_pr(w.db, w.requester, pr)
    assert w.db.get(PurchaseRequest, pr_id) is None


def test_submitted_pr_cannot_be_deleted(w):
    pr = w.submitted()
    with pytest.raises(InvalidTransition, match="Cannot delete .* it is PENDING_DEPT_HEAD"):
        pr_service.delete_pr(w.db, w.requester, pr)


def test_only_the_owner_can_delete(w):
    with pytest.raises(Forbidden):
        pr_service.delete_pr(w.db, w.requester_ops, _create(w))


# ---- submit -------------------------------------------------------------------------------------


def test_requester_submits_to_the_dept_head(w):
    pr = pr_service.submit_pr(w.db, w.requester, _create(w))
    assert pr.status is PRStatus.PENDING_DEPT_HEAD
    assert pr.submitted_at == clock.now()
    assert w.audit(pr)[-1] == ("SUBMITTED", "DRAFT", "PENDING_DEPT_HEAD")


def test_only_the_owner_can_submit(w):
    with pytest.raises(Forbidden, match="can submit it"):
        pr_service.submit_pr(w.db, w.head, _create(w))


def test_submitting_twice_is_an_invalid_transition(w):
    pr = w.submitted()
    with pytest.raises(InvalidTransition, match="Cannot submit .* it is PENDING_DEPT_HEAD"):
        pr_service.submit_pr(w.db, w.requester, pr)


def test_a_stale_draft_cannot_be_submitted_after_its_required_by_date(w):
    pr = _create(w)
    w.later(days=11)
    with pytest.raises(BusinessRuleViolation, match="is in the past"):
        pr_service.submit_pr(w.db, w.requester, pr)


def test_fractional_quantities_round_line_amounts_to_the_paisa(w):
    """D-53: 1.5 kg × ₹10.01 = ₹15.015 → ₹15.02 (half up); totals are sums of rounded lines."""
    pr = w.draft(lines=(("MS Steel Rod 12 mm", "1.5", "10.01"), (MOUSE, "3", "0.35")))
    assert pr.estimated_total == Decimal("16.07")  # 15.02 + 1.05
    assert (pr.lines[0].quantity, pr.lines[0].estimated_unit_price) == (Decimal("1.500"), Decimal("10.01"))
    assert str(pr.estimated_total) == "16.07"
