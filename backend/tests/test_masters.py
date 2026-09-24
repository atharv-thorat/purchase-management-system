"""Master data rules: D-10 (suppliers), D-19 (departments only for REQUESTER/DEPT_HEAD),
D-22 (one role), D-23 (deactivate, never delete) and settings."""

import pytest

from app.core.errors import BusinessRuleViolation, Forbidden
from app.core.security import verify_password
from app.models.enums import Role
from app.services import master_service as ms


def test_admin_creates_a_requester_in_a_department(w):
    it = w.requester.department
    user = ms.create_user(w.db, w.admin, name="New Hire", email="New.Hire@Example.com", password="secret1",
                          role=Role.REQUESTER, department_id=it.id)
    assert (user.email, user.department, user.is_active) == ("new.hire@example.com", it, True)
    assert verify_password("secret1", user.password_hash)


@pytest.mark.parametrize("role, dept, message", [
    (Role.REQUESTER, None, "A REQUESTER must belong to a department"),
    (Role.DEPT_HEAD, None, "A DEPT_HEAD must belong to a department"),
    (Role.FINANCE, "IT", "A FINANCE user acts across departments and cannot belong to one"),
    (Role.ADMIN, "IT", "cannot belong to one"),
    ("SUPERUSER", None, "Role must be one of"),
])
def test_department_is_required_exactly_for_department_roles(w, role, dept, message):
    dept_id = w.requester.department_id if dept else None
    with pytest.raises(BusinessRuleViolation, match=message):
        ms.create_user(w.db, w.admin, name="X", email="x@example.com", password="secret1", role=role,
                       department_id=dept_id)


def test_changing_role_moves_the_department_rule_with_it(w):
    with pytest.raises(BusinessRuleViolation, match="cannot belong to one"):
        ms.update_user(w.db, w.admin, w.requester, role=Role.STORE)
    ms.update_user(w.db, w.admin, w.requester, role=Role.STORE, department_id=None)
    assert (w.requester.role, w.requester.department) == (Role.STORE, None)


def test_email_must_be_valid_and_unique(w):
    with pytest.raises(BusinessRuleViolation, match="already exists"):
        ms.create_user(w.db, w.admin, name="X", email="FINANCE@example.com", password="secret1", role=Role.FINANCE)
    with pytest.raises(BusinessRuleViolation, match="not a valid email"):
        ms.create_user(w.db, w.admin, name="X", email="nope", password="secret1", role=Role.FINANCE)
    with pytest.raises(BusinessRuleViolation, match="at least 6 characters"):
        ms.create_user(w.db, w.admin, name="X", email="x@example.com", password="123", role=Role.FINANCE)


def test_users_are_deactivated_not_deleted_and_admin_cannot_lock_themselves_out(w):
    ms.update_user(w.db, w.admin, w.store, is_active=False)
    assert w.store.is_active is False
    with pytest.raises(Forbidden, match="cannot deactivate yourself"):
        ms.update_user(w.db, w.admin, w.admin, is_active=False)
    with pytest.raises(Forbidden, match="change your own role"):
        ms.update_user(w.db, w.admin, w.admin, role=Role.FINANCE)


def test_supplier_gstin_is_validated_and_unique(w):
    s = ms.create_supplier(w.db, w.admin, name="Acme", contact_person="A", email="a@acme.in", phone="1",
                           gstin="27aabca1234d1z5")
    assert s.gstin == "27AABCA1234D1Z5" and s.is_active
    with pytest.raises(BusinessRuleViolation, match="not a valid 15-character GSTIN"):
        ms.create_supplier(w.db, w.admin, name="B", contact_person="B", email="b", phone="1", gstin="1234")
    with pytest.raises(BusinessRuleViolation, match="already registered to Acme"):
        ms.create_supplier(w.db, w.admin, name="C", contact_person="C", email="c", phone="1", gstin="27AABCA1234D1Z5")


def test_supplier_is_deactivated_not_deleted(w):
    s = w.suppliers["Bharat Office Supplies"]
    ms.update_supplier(w.db, w.admin, s, is_active=False)
    assert s.is_active is False


def test_department_and_item_names_are_unique_ignoring_case(w):
    with pytest.raises(BusinessRuleViolation, match="department named IT already exists"):
        ms.create_department(w.db, w.admin, name="it", monthly_budget="1")
    with pytest.raises(BusinessRuleViolation, match="already exists"):
        ms.create_item(w.db, w.admin, name="wireless mouse", unit="pcs", category="x")
    with pytest.raises(BusinessRuleViolation, match="Unit must be one of pcs, kg, box"):
        ms.create_item(w.db, w.admin, name="Chair", unit="dozen", category="x")
    assert ms.update_department(w.db, w.admin, w.requester.department, monthly_budget="1500000").monthly_budget == 1500000


def test_unknown_setting_is_refused(w):
    with pytest.raises(BusinessRuleViolation, match="Unknown setting 'MAX_LAPTOPS'"):
        ms.set_setting(w.db, w.admin, "MAX_LAPTOPS", "3")
    assert ms.finance_threshold(w.db) == 50000
