"""Rule 6 (selection rules), D-14 (expired quotes), D-33 (select + PO is one atomic action)."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden, InvalidTransition
from app.models import PurchaseOrder
from app.models.enums import PRStatus
from app.services import master_service, quotation_service
from tests.conftest import DIGITAL, INFOLINE, LAPTOP, TECHNO


def _select(w, pr, q, **kw):
    return quotation_service.select_quotation(w.db, w.purchase, pr, q, **kw)


def _three_quotes(w):
    pr = w.approved()
    return pr, (w.quote(pr, TECHNO, {LAPTOP: "900"}), w.quote(pr, DIGITAL, {LAPTOP: "950"}),
                w.quote(pr, INFOLINE, {LAPTOP: "900"}))


def test_single_quotation_needs_a_justification(w):
    pr = w.approved()
    q = w.quote(pr)
    with pytest.raises(BusinessRuleViolation, match="has only one valid quotation; a single-quote justification is required"):
        _select(w, pr, q, single_quote_justification="  ")
    po = _select(w, pr, q, single_quote_justification="Only authorised dealer")
    assert po.single_quote_justification == "Only authorised dealer"


def test_lowest_quotation_needs_no_reason(w):
    pr, (techno, _digital, _infoline) = _three_quotes(w)
    po = _select(w, pr, techno)
    assert po.selection_reason is None and po.single_quote_justification is None


def test_a_tie_for_lowest_counts_as_lowest(w):
    pr, (_techno, _digital, infoline) = _three_quotes(w)
    assert _select(w, pr, infoline).supplier.name == INFOLINE


def test_non_lowest_quotation_needs_a_selection_reason(w):
    pr, (_techno, digital, _infoline) = _three_quotes(w)
    with pytest.raises(BusinessRuleViolation) as exc:
        _select(w, pr, digital)
    assert exc.value.message == (f"The quotation from {DIGITAL} (₹9,500.00) is not the lowest valid one "
                                 f"(₹9,000.00 from {TECHNO}); a selection reason is required")
    po = _select(w, pr, digital, selection_reason="Faster delivery, better warranty")
    assert po.selection_reason == "Faster delivery, better warranty"


def test_expired_quotation_cannot_be_selected(w):
    pr = w.approved()
    q = w.quote(pr, valid_days=5)
    w.later(days=6)
    with pytest.raises(BusinessRuleViolation, match=f"The quotation from {TECHNO} expired on 20 Sep 2026"):
        _select(w, pr, q, single_quote_justification="x")


def test_quotation_valid_until_today_can_still_be_selected(w):
    pr = w.approved()
    q = w.quote(pr, valid_days=5)
    w.later(days=5)
    assert _select(w, pr, q, single_quote_justification="x").status == "ISSUED"


def test_expired_quotation_does_not_set_the_lowest_price(w):
    """D-50: an expired quote can't be picked, so undercutting it needs no selection reason."""
    pr = w.approved()
    w.quote(pr, TECHNO, {LAPTOP: "800"}, valid_days=1)
    mid = w.quote(pr, DIGITAL, {LAPTOP: "900"})
    dear = w.quote(pr, INFOLINE, {LAPTOP: "950"})
    w.later(days=2)
    with pytest.raises(BusinessRuleViolation, match=f"not the lowest valid one \\(₹9,000.00 from {DIGITAL}\\)"):
        _select(w, pr, dear)
    po = _select(w, pr, mid)
    assert po.selection_reason is None and po.single_quote_justification is None


def test_expired_quotations_do_not_count_toward_two_quotes(w):
    """D-50: one valid quote plus an expired one is still a single-quote purchase."""
    pr = w.approved()
    w.quote(pr, TECHNO, {LAPTOP: "800"}, valid_days=1)
    only = w.quote(pr, DIGITAL, {LAPTOP: "900"})
    w.later(days=2)
    with pytest.raises(BusinessRuleViolation) as exc:
        _select(w, pr, only)
    assert exc.value.message == (f"{pr.pr_number} has only one valid quotation (1 expired quotation not counted); "
                                 "a single-quote justification is required")
    po = _select(w, pr, only, single_quote_justification="Other quote lapsed; supplier will not extend")
    assert po.selection_reason is None


def test_supplier_deactivated_after_quoting_cannot_be_selected(w):
    pr = w.approved()
    q = w.quote(pr)
    master_service.update_supplier(w.db, w.admin, w.suppliers[TECHNO], is_active=False)
    with pytest.raises(BusinessRuleViolation, match="is inactive and cannot be selected"):
        _select(w, pr, q, single_quote_justification="x")


def test_quotation_of_another_pr_is_refused(w):
    pr, other = w.approved(), w.approved()
    q = w.quote(other)
    with pytest.raises(BusinessRuleViolation, match=f"does not belong to {pr.pr_number}"):
        _select(w, pr, q, single_quote_justification="x")


def test_second_selection_is_an_invalid_transition(w):
    pr, (techno, digital, _) = _three_quotes(w)
    _select(w, pr, techno)
    with pytest.raises(InvalidTransition, match="Cannot create a purchase order for .* it is PO_CREATED"):
        _select(w, pr, digital, selection_reason="x")


@pytest.mark.parametrize("role", ["requester", "head", "finance", "store", "accounts", "admin"])
def test_only_purchase_selects(w, role):
    pr = w.approved()
    q = w.quote(pr)
    with pytest.raises(Forbidden, match="Only PURCHASE users can select quotations"):
        quotation_service.select_quotation(w.db, getattr(w, role), pr, q, single_quote_justification="x")


def test_failed_selection_changes_nothing(w):
    pr, (_techno, digital, _) = _three_quotes(w)
    with pytest.raises(BusinessRuleViolation):
        _select(w, pr, digital)
    assert pr.status is PRStatus.APPROVED
    assert not any(q.is_selected for q in pr.quotations)
    assert w.db.query(PurchaseOrder).count() == 0
    assert w.po().po_number == "PO-0001"  # no number was used up
