"""Segregation of duties at the service layer: ADMIN takes no transactional action (D-09), each
action belongs to exactly its role, and deactivated users can't act (D-23). The API layer adds
the same checks through require_roles; these tests prove the services hold on their own."""

from datetime import timedelta

import pytest

from app.core import clock
from app.core.errors import Forbidden
from app.models.enums import Role
from app.services import (
    grn_service,
    invoice_service,
    master_service,
    payment_service,
    po_service,
    pr_service,
    quotation_service,
)
from app.services.grn_service import GRNLineIn
from app.services.pr_service import PRLineIn
from tests.conftest import LAPTOP

TODAY = lambda: clock.today()  # noqa: E731


def _actions(w):
    """(name, owning roles, call(actor)) for every transactional service action."""
    pending = w.submitted()
    approved = w.approved()
    q = w.quote(approved)
    po = w.po()
    received = w.po()
    w.receive(received, accept={LAPTOP: "5"})
    matched_po = w.po()
    w.receive(matched_po)
    matched = w.invoice(matched_po, "M-1")
    mismatch = w.invoice(received, "X-1", lines={LAPTOP: ("9", "1000")})
    return [
        ("create PR", {Role.REQUESTER, Role.DEPT_HEAD},
         lambda a: pr_service.create_pr(w.db, a, justification="x", required_by=TODAY() + timedelta(days=5),
                                        lines=[PRLineIn(w.items[LAPTOP].id, 1, 1)])),
        ("approve PR", {Role.DEPT_HEAD}, lambda a: pr_service.approve_pr(w.db, a, pending)),
        ("reject PR", {Role.DEPT_HEAD}, lambda a: pr_service.reject_pr(w.db, a, pending, comment="x")),
        ("add quotation", {Role.PURCHASE},
         lambda a: quotation_service.add_quotation(w.db, a, approved, supplier_id=w.suppliers["Digital Edge Systems"].id,
                                                   quote_date=TODAY(), valid_until=TODAY(), delivery_days=1,
                                                   payment_terms="x", lines=[])),
        ("select quotation", {Role.PURCHASE},
         lambda a: quotation_service.select_quotation(w.db, a, approved, q, single_quote_justification="x")),
        ("cancel PO", {Role.PURCHASE}, lambda a: po_service.cancel_po(w.db, a, po, reason="x")),
        ("short-close PO", {Role.PURCHASE}, lambda a: po_service.short_close_po(w.db, a, received, reason="x")),
        ("record GRN", {Role.STORE},
         lambda a: grn_service.record_grn(w.db, a, po, received_date=TODAY(),
                                          lines=[GRNLineIn(po.lines[0].id, "1", "1")])),
        ("enter invoice", {Role.ACCOUNTS},
         lambda a: invoice_service.enter_invoice(w.db, a, received, supplier_invoice_number="N-1",
                                                 invoice_date=TODAY(), total="1000", lines=[])),
        ("rematch invoice", {Role.ACCOUNTS}, lambda a: invoice_service.rematch_invoice(w.db, a, mismatch)),
        ("reject invoice", {Role.ACCOUNTS}, lambda a: invoice_service.reject_invoice(w.db, a, mismatch, reason="x")),
        ("record payment", {Role.ACCOUNTS},
         lambda a: payment_service.record_payment(w.db, a, matched, amount="1", mode="NEFT", reference_no="x",
                                                  paid_on=TODAY())),
    ]


def _actor(w, role: Role):
    return {Role.REQUESTER: w.requester_ops, Role.DEPT_HEAD: w.head_ops, Role.FINANCE: w.finance,
            Role.PURCHASE: w.purchase, Role.STORE: w.store, Role.ACCOUNTS: w.accounts, Role.ADMIN: w.admin}[role]


def test_admin_can_take_no_transactional_action(w):
    for name, _roles, call in _actions(w):
        with pytest.raises(Forbidden, match="you are ADMIN"):
            call(w.admin)
        assert name


@pytest.mark.parametrize("role", [r for r in Role if r is not Role.ADMIN])
def test_each_action_refuses_every_role_that_does_not_own_it(w, role):
    actor = _actor(w, role)
    refused = 0
    for name, owners, call in _actions(w):
        # FINANCE also approves/rejects (at its own level); approver-level rules are tested elsewhere
        if role in owners or (role is Role.FINANCE and name in ("approve PR", "reject PR")):
            continue
        with pytest.raises(Forbidden):
            call(actor)
        refused += 1
    assert refused > 0


def test_deactivated_users_cannot_act(w):
    pr = w.submitted()
    w.head.is_active = False
    with pytest.raises(Forbidden, match="Your account is deactivated"):
        pr_service.approve_pr(w.db, w.head, pr)


@pytest.mark.parametrize("role", [r for r in Role if r is not Role.ADMIN])
def test_only_admin_manages_master_data(w, role):
    actor = _actor(w, role)
    with pytest.raises(Forbidden, match="Only ADMIN users can create suppliers"):
        master_service.create_supplier(w.db, actor, name="X", contact_person="Y", email="x@y.in", phone="1",
                                       gstin="27AAACT2727Q1ZX")
    with pytest.raises(Forbidden, match="Only ADMIN users can change settings"):
        master_service.set_setting(w.db, actor, "FINANCE_APPROVAL_THRESHOLD", "1")
    with pytest.raises(Forbidden, match="Only ADMIN users can manage users"):
        master_service.create_user(w.db, actor, name="X", email="x@y.in", password="secret1", role=Role.STORE)
