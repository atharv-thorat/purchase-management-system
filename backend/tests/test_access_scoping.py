"""Read visibility per role (D-08), DRAFT privacy (D-45), 404 vs 403 (D-37) — over the demo data."""

import pytest
from sqlalchemy import func, select

from app.core.errors import Forbidden, NotFound
from app.models import AuditLog, GoodsReceipt, Invoice, Payment, PurchaseOrder, PurchaseRequest, Quotation
from app.models.enums import EntityType
from app.seed.seed import seed
from app.services import access
from tests.conftest import NOW

MODELS = [PurchaseRequest, Quotation, PurchaseOrder, GoodsReceipt, Invoice, Payment]


@pytest.fixture
def demo(db, password_hash):
    return seed(db, password_hash=password_hash, now=NOW)


def _visible(db, model, user):
    try:
        rows = db.scalars(access.scoped_select(model, user)).all()
    except Forbidden:
        return "403"
    return sorted(getattr(r, "pr_number", None) or getattr(r, "po_number", None) or getattr(r, "grn_number", None)
                  or r.id for r in rows)


# PRs: PR-0001..3 and 0005 are APPROVED/PO_CREATED; 0004 REJECTED (Ops), 0006 PENDING_FINANCE (IT head's),
# 0007 PENDING_DEPT_HEAD (Ops), 0008 is Riya's DRAFT.
@pytest.mark.parametrize("user, expected_prs", [
    ("requester.it", ["PR-0001", "PR-0002", "PR-0005", "PR-0008"]),
    ("head.it", ["PR-0001", "PR-0002", "PR-0005", "PR-0006"]),  # not Riya's draft
    ("requester.ops", ["PR-0003", "PR-0004", "PR-0007"]),
    ("head.ops", ["PR-0003", "PR-0004", "PR-0007"]),
    ("finance", ["PR-0001", "PR-0002", "PR-0003", "PR-0004", "PR-0005", "PR-0006", "PR-0007"]),
    ("purchase", ["PR-0001", "PR-0002", "PR-0003", "PR-0005"]),  # APPROVED onwards
    ("store", "403"),
    ("accounts", "403"),
    ("admin", ["PR-0001", "PR-0002", "PR-0003", "PR-0004", "PR-0005", "PR-0006", "PR-0007"]),
])
def test_pr_visibility(db, demo, user, expected_prs):
    assert _visible(db, PurchaseRequest, demo.users[user]) == expected_prs


@pytest.mark.parametrize("user, pos, grns, invoices, payments, quotations", [
    ("requester.it", ["PO-0001", "PO-0002"], ["GRN-0001", "GRN-0002"], 3, 2, "403"),
    ("head.ops", ["PO-0003"], ["GRN-0003"], 1, 0, "403"),
    ("finance", ["PO-0001", "PO-0002", "PO-0003"], "403", 4, 2, 8),
    ("purchase", ["PO-0001", "PO-0002", "PO-0003"], ["GRN-0001", "GRN-0002", "GRN-0003"], 4, "403", 8),
    ("store", ["PO-0001", "PO-0002", "PO-0003"], ["GRN-0001", "GRN-0002", "GRN-0003"], "403", "403", "403"),
    ("accounts", ["PO-0001", "PO-0002", "PO-0003"], ["GRN-0001", "GRN-0002", "GRN-0003"], 4, 2, "403"),
    ("admin", ["PO-0001", "PO-0002", "PO-0003"], ["GRN-0001", "GRN-0002", "GRN-0003"], 4, 2, 8),
])
def test_linked_document_visibility(db, demo, user, pos, grns, invoices, payments, quotations):
    u = demo.users[user]
    count = lambda m: (lambda v: v if v == "403" else len(v))(_visible(db, m, u))  # noqa: E731
    assert _visible(db, PurchaseOrder, u) == pos
    assert _visible(db, GoodsReceipt, u) == grns
    assert (count(Invoice), count(Payment), count(Quotation)) == (invoices, payments, quotations)


def test_draft_is_404_for_everyone_but_its_author(db, demo):
    draft = db.scalar(select(PurchaseRequest).where(PurchaseRequest.pr_number == "PR-0008"))
    assert access.get_visible_or_404(db, PurchaseRequest, draft.id, demo.users["requester.it"]) is draft
    for user in ("head.it", "finance", "admin", "purchase"):
        with pytest.raises(NotFound, match=f"Purchase request {draft.id} not found"):
            access.get_visible_or_404(db, PurchaseRequest, draft.id, demo.users[user])


def test_draft_audit_rows_are_hidden_from_everyone_but_the_author(db, demo):
    draft = db.scalar(select(PurchaseRequest).where(PurchaseRequest.pr_number == "PR-0008"))

    def sees_draft_history(user):
        return db.scalar(select(func.count()).select_from(AuditLog).where(
            access.audit_visible_filter(demo.users[user]),
            AuditLog.entity_type == EntityType.PURCHASE_REQUEST, AuditLog.entity_id == draft.id)) > 0

    assert sees_draft_history("requester.it")
    assert not any(sees_draft_history(u) for u in ("head.it", "finance", "admin"))


def test_out_of_scope_is_404_and_role_without_access_is_403(db, demo):
    po3 = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-0003"))
    assert access.get_visible_or_404(db, PurchaseOrder, po3.id, demo.users["requester.ops"]) is po3
    with pytest.raises(NotFound, match=f"Purchase order {po3.id} not found"):
        access.get_visible_or_404(db, PurchaseOrder, po3.id, demo.users["requester.it"])
    with pytest.raises(NotFound):
        access.get_visible_or_404(db, PurchaseOrder, 9999, demo.users["admin"])
    with pytest.raises(Forbidden, match=r"Your role \(STORE\) cannot view purchase requests"):
        access.get_visible_or_404(db, PurchaseRequest, 1, demo.users["store"])


def test_audit_rows_follow_entity_visibility(db, demo):
    def entity_types(user):
        rows = db.scalars(select(AuditLog).where(access.audit_visible_filter(demo.users[user])))
        return {r.entity_type for r in rows}

    assert entity_types("store") == {EntityType.PURCHASE_ORDER}
    assert entity_types("accounts") == {EntityType.PURCHASE_ORDER, EntityType.INVOICE}
    ops_rows = db.scalars(select(AuditLog).where(access.audit_visible_filter(demo.users["requester.ops"]))).all()
    ops_prs = {pr.id for pr in db.scalars(select(PurchaseRequest).where(PurchaseRequest.department_id == 2))}
    assert {r.entity_id for r in ops_rows if r.entity_type is EntityType.PURCHASE_REQUEST} <= ops_prs
