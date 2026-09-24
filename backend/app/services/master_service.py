"""Master data (ADMIN only, D-09/D-10) and settings."""

import re
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import atomic
from app.core.errors import BusinessRuleViolation, Forbidden, NotFound
from app.core.security import hash_password
from app.models.enums import DEPARTMENT_ROLES, SETTING_DEFAULTS, ItemUnit, Role, SettingKey
from app.models.master import Department, Item, Setting, Supplier, User
from app.services._common import ensure_role, money, require_text

GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UNSET = object()


def _admin(actor: User, to: str) -> None:
    ensure_role(actor, Role.ADMIN, to=to)


# ---- settings -------------------------------------------------------------------------------


def get_setting(db: Session, key: SettingKey) -> str:
    row = db.get(Setting, key.value)
    return row.value if row else SETTING_DEFAULTS[key]


def list_settings(db: Session) -> list[tuple[str, str]]:
    """Every known setting with its stored value, or its default when never set."""
    return [(key.value, get_setting(db, key)) for key in SettingKey]


def finance_threshold(db: Session) -> Decimal:
    return Decimal(get_setting(db, SettingKey.FINANCE_APPROVAL_THRESHOLD))


@atomic
def set_setting(db: Session, actor: User, key: str, value: str) -> Setting:
    _admin(actor, "change settings")
    try:
        known = SettingKey(key)
    except ValueError:
        raise BusinessRuleViolation(f"Unknown setting {key!r}") from None
    if known is SettingKey.FINANCE_APPROVAL_THRESHOLD:
        value = str(money(value, "The finance approval threshold", allow_zero=True))
    row = db.get(Setting, known.value)
    if row is None:
        row = Setting(key=known.value, value=value)
        db.add(row)
    else:
        row.value = value
    db.flush()
    return row


# ---- departments ----------------------------------------------------------------------------


def _unique_department_name(db: Session, name: str, exclude_id: int | None = None) -> str:
    name = require_text(name, "Department name")
    clash = db.scalar(select(Department).where(func.lower(Department.name) == name.lower()))
    if clash is not None and clash.id != exclude_id:
        raise BusinessRuleViolation(f"A department named {clash.name} already exists")
    return name


@atomic
def create_department(db: Session, actor: User, *, name: str, monthly_budget) -> Department:
    _admin(actor, "manage departments")
    dept = Department(
        name=_unique_department_name(db, name),
        monthly_budget=money(monthly_budget, "Monthly budget", allow_zero=True),
    )
    db.add(dept)
    db.flush()
    return dept


@atomic
def update_department(db: Session, actor: User, dept: Department, *, name=None, monthly_budget=None) -> Department:
    _admin(actor, "manage departments")
    if name is not None:
        dept.name = _unique_department_name(db, name, exclude_id=dept.id)
    if monthly_budget is not None:
        dept.monthly_budget = money(monthly_budget, "Monthly budget", allow_zero=True)
    db.flush()
    return dept


# ---- users ----------------------------------------------------------------------------------


def _check_department_for_role(db: Session, role: Role, department_id: int | None) -> Department | None:
    """REQUESTER and DEPT_HEAD need a department; every other role has none (D-19)."""
    if role in DEPARTMENT_ROLES:
        if department_id is None:
            raise BusinessRuleViolation(f"A {role} must belong to a department")
        dept = db.get(Department, department_id)
        if dept is None:
            raise NotFound(f"Department {department_id} not found")
        return dept
    if department_id is not None:
        raise BusinessRuleViolation(f"A {role} user acts across departments and cannot belong to one")
    return None


def _unique_email(db: Session, email: str, exclude_id: int | None = None) -> str:
    email = require_text(email, "Email").lower()
    if not EMAIL_PATTERN.match(email):
        raise BusinessRuleViolation(f"{email!r} is not a valid email address")
    clash = db.scalar(select(User).where(func.lower(User.email) == email))
    if clash is not None and clash.id != exclude_id:
        raise BusinessRuleViolation(f"A user with email {email} already exists")
    return email


def _role(value) -> Role:
    try:
        return Role(value)
    except ValueError:
        raise BusinessRuleViolation(f"Role must be one of {', '.join(r.value for r in Role)}") from None


def _password(value: str) -> str:
    if len(value or "") < 6:
        raise BusinessRuleViolation("Password must be at least 6 characters")
    return hash_password(value)


@atomic
def create_user(db: Session, actor: User, *, name: str, email: str, password: str, role: Role,
                department_id: int | None = None) -> User:
    _admin(actor, "manage users")
    role = _role(role)
    user = User(
        name=require_text(name, "Name"),
        email=_unique_email(db, email),
        password_hash=_password(password),
        role=role,  # exactly one role per user (D-22)
        department=_check_department_for_role(db, role, department_id),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@atomic
def update_user(db: Session, actor: User, user: User, *, name=None, email=None, role=None,
                department_id=_UNSET, is_active=None, password=None) -> User:
    _admin(actor, "manage users")
    if user.id == actor.id and ((is_active is False) or (role is not None and _role(role) is not actor.role)):
        raise Forbidden("You cannot deactivate yourself or change your own role")
    if name is not None:
        user.name = require_text(name, "Name")
    if email is not None:
        user.email = _unique_email(db, email, exclude_id=user.id)
    if role is not None or department_id is not _UNSET:
        new_role = _role(role) if role is not None else user.role
        new_dept_id = user.department_id if department_id is _UNSET else department_id
        user.department = _check_department_for_role(db, new_role, new_dept_id)
        user.role = new_role
    if is_active is not None:
        user.is_active = is_active  # deactivate, never delete (D-23)
    if password is not None:
        user.password_hash = _password(password)
    db.flush()
    return user


# ---- suppliers ------------------------------------------------------------------------------


def _unique_gstin(db: Session, gstin: str, exclude_id: int | None = None) -> str:
    gstin = require_text(gstin, "GSTIN").upper()
    if not GSTIN_PATTERN.match(gstin):
        raise BusinessRuleViolation(f"{gstin!r} is not a valid 15-character GSTIN")
    clash = db.scalar(select(Supplier).where(Supplier.gstin == gstin))
    if clash is not None and clash.id != exclude_id:
        raise BusinessRuleViolation(f"GSTIN {gstin} is already registered to {clash.name}")
    return gstin


@atomic
def create_supplier(db: Session, actor: User, *, name: str, contact_person: str, email: str, phone: str,
                    gstin: str) -> Supplier:
    _admin(actor, "create suppliers")  # D-10
    supplier = Supplier(
        name=require_text(name, "Supplier name"),
        contact_person=require_text(contact_person, "Contact person"),
        email=require_text(email, "Email"),
        phone=require_text(phone, "Phone"),
        gstin=_unique_gstin(db, gstin),
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return supplier


@atomic
def update_supplier(db: Session, actor: User, supplier: Supplier, *, name=None, contact_person=None, email=None,
                    phone=None, gstin=None, is_active=None) -> Supplier:
    _admin(actor, "manage suppliers")
    for attr, value, what in (
        ("name", name, "Supplier name"),
        ("contact_person", contact_person, "Contact person"),
        ("email", email, "Email"),
        ("phone", phone, "Phone"),
    ):
        if value is not None:
            setattr(supplier, attr, require_text(value, what))
    if gstin is not None:
        supplier.gstin = _unique_gstin(db, gstin, exclude_id=supplier.id)
    if is_active is not None:
        supplier.is_active = is_active  # deactivate, never delete (D-10)
    db.flush()
    return supplier


# ---- items ----------------------------------------------------------------------------------


def _unique_item_name(db: Session, name: str, exclude_id: int | None = None) -> str:
    name = require_text(name, "Item name")
    clash = db.scalar(select(Item).where(func.lower(Item.name) == name.lower()))
    if clash is not None and clash.id != exclude_id:
        raise BusinessRuleViolation(f"An item named {clash.name} already exists")
    return name


def _unit(unit) -> ItemUnit:
    try:
        return ItemUnit(unit)
    except ValueError:
        raise BusinessRuleViolation(f"Unit must be one of {', '.join(u.value for u in ItemUnit)}") from None


@atomic
def create_item(db: Session, actor: User, *, name: str, unit, category: str) -> Item:
    _admin(actor, "manage items")
    item = Item(name=_unique_item_name(db, name), unit=_unit(unit), category=require_text(category, "Category"))
    db.add(item)
    db.flush()
    return item


@atomic
def update_item(db: Session, actor: User, item: Item, *, name=None, unit=None, category=None) -> Item:
    _admin(actor, "manage items")
    if name is not None:
        item.name = _unique_item_name(db, name, exclude_id=item.id)
    if unit is not None:
        item.unit = _unit(unit)
    if category is not None:
        item.category = require_text(category, "Category")
    db.flush()
    return item
