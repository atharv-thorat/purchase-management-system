"""The transition tables (D-27): exhaustive allowed/forbidden checks and error messages."""

import pytest

from app.core.errors import InvalidTransition
from app.models import Invoice, PurchaseOrder, PurchaseRequest
from app.models.enums import AuditAction, InvoiceStatus, POStatus, PRStatus
from app.services import state_machine as sm

ENTITIES = [
    (lambda s: PurchaseRequest(pr_number="PR-0042", status=s), PRStatus, sm.PR_TRANSITIONS),
    (lambda s: PurchaseOrder(po_number="PO-0042", status=s), POStatus, sm.PO_TRANSITIONS),
    (lambda s: Invoice(supplier_invoice_number="INV-42", status=s), InvoiceStatus, sm.INVOICE_TRANSITIONS),
]


def _all_cases():
    for make, statuses, table in ENTITIES:
        for status in statuses:
            for action in AuditAction:
                yield pytest.param(make, status, action, (status, action) in table,
                                   id=f"{statuses.__name__}.{status}-{action}")


@pytest.mark.parametrize("make, status, action, allowed", list(_all_cases()))
def test_every_status_action_pair_is_allowed_only_if_in_the_table(make, status, action, allowed):
    entity = make(status)
    if allowed:
        assert sm.check(entity, action)
    else:
        with pytest.raises(InvalidTransition, match=rf"^Cannot .* it is {status}"):
            sm.check(entity, action)


def test_invalid_transition_message_names_action_record_status_and_allowed_states():
    pr = PurchaseRequest(pr_number="PR-0001", status=PRStatus.DRAFT)
    with pytest.raises(InvalidTransition) as exc:
        sm.check(pr, AuditAction.APPROVED)
    assert exc.value.message == ("Cannot approve purchase request PR-0001: it is DRAFT "
                                 "(allowed only when PENDING_DEPT_HEAD or PENDING_FINANCE)")
    assert exc.value.status_code == 409


def test_target_outside_the_allowed_set_is_refused(db):
    pr = PurchaseRequest(pr_number="PR-0001", status=PRStatus.PENDING_FINANCE)
    with pytest.raises(InvalidTransition, match="cannot move to PENDING_FINANCE"):
        sm.transition(db, pr, AuditAction.APPROVED, PRStatus.PENDING_FINANCE, None)


@pytest.mark.parametrize("entity, terminal", [
    (PurchaseOrder, {POStatus.CLOSED, POStatus.CANCELLED}),
    (Invoice, {InvoiceStatus.PAID, InvoiceStatus.REJECTED}),
])
def test_terminal_states_have_no_way_out(entity, terminal):
    _, table = sm.TABLES[entity]
    assert not [key for key in table if key[0] in terminal]


def test_every_non_terminal_status_has_an_outgoing_action():
    for _, statuses, table in ENTITIES:
        with_exit = {status for (status, _action), targets in table.items() if targets - {status}}
        dead_ends = set(statuses) - with_exit
        assert dead_ends <= {POStatus.CLOSED, POStatus.CANCELLED, InvoiceStatus.PAID, InvoiceStatus.REJECTED}


def test_allowed_actions_lists_what_the_ui_may_offer():
    po = PurchaseOrder(po_number="PO-1", status=POStatus.PARTIALLY_RECEIVED)
    assert set(sm.allowed_actions(po)) == {AuditAction.GRN_RECORDED, AuditAction.SHORT_CLOSED}
    assert sm.allowed_actions(Invoice(supplier_invoice_number="X", status=InvoiceStatus.PAID)) == []


def test_require_status_guard_message():
    po = PurchaseOrder(po_number="PO-0007", status=POStatus.ISSUED)
    with pytest.raises(InvalidTransition) as exc:
        sm.require_status(po, {POStatus.FULLY_RECEIVED, POStatus.SHORT_CLOSED}, "enter an invoice against")
    assert exc.value.message == ("Cannot enter an invoice against purchase order PO-0007: it is ISSUED "
                                 "(allowed only when FULLY_RECEIVED or SHORT_CLOSED)")
