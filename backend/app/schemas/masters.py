from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ItemUnit, Role
from app.schemas.common import ORM, DepartmentRef


class DepartmentOut(ORM):
    id: int
    name: str
    monthly_budget: Decimal


class DepartmentIn(BaseModel):
    name: str
    monthly_budget: Decimal


class DepartmentUpdate(BaseModel):
    name: str | None = None
    monthly_budget: Decimal | None = None


class UserAdminOut(ORM):
    id: int
    name: str
    email: str
    role: Role
    department: DepartmentRef | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Role
    department_id: int | None = None


class UserUpdate(BaseModel):
    """Only fields present in the request are changed; send department_id: null to clear it."""

    name: str | None = None
    email: str | None = None
    role: Role | None = None
    department_id: int | None = None
    is_active: bool | None = None
    password: str | None = None


class SupplierOut(ORM):
    id: int
    name: str
    contact_person: str
    email: str
    phone: str
    gstin: str
    is_active: bool


class SupplierIn(BaseModel):
    name: str
    contact_person: str
    email: str
    phone: str
    gstin: str


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    gstin: str | None = None
    is_active: bool | None = None


class ItemOut(ORM):
    id: int
    name: str
    unit: ItemUnit
    category: str


class ItemIn(BaseModel):
    name: str
    unit: ItemUnit
    category: str


class ItemUpdate(BaseModel):
    name: str | None = None
    unit: ItemUnit | None = None
    category: str | None = None


class SettingOut(ORM):
    key: str
    value: str


class SettingIn(BaseModel):
    value: str
