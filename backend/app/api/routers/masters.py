"""Master data: departments, users, suppliers, items, settings. Writes are ADMIN only (D-09, D-10)."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.common import ERROR_RESPONSES, READ_ROLES, Allow
from app.core.deps import DbSession
from app.core.errors import NotFound
from app.models import Department, Item, Supplier, User
from app.models.enums import Role
from app.schemas.masters import (
    DepartmentIn,
    DepartmentOut,
    DepartmentUpdate,
    ItemIn,
    ItemOut,
    ItemUpdate,
    SettingIn,
    SettingOut,
    SupplierIn,
    SupplierOut,
    SupplierUpdate,
    UserAdminOut,
    UserCreate,
    UserUpdate,
)
from app.services import master_service

router = APIRouter(tags=["masters"], responses=ERROR_RESPONSES)
AD, F, P, A = Role.ADMIN, Role.FINANCE, Role.PURCHASE, Role.ACCOUNTS


def _get(db, model, record_id: int, label: str):
    obj = db.get(model, record_id)
    if obj is None:
        raise NotFound(f"{label} {record_id} not found")
    return obj


# ---- departments ----------------------------------------------------------------------------------


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: DbSession, _: Allow(*READ_ROLES)):
    return db.scalars(select(Department).order_by(Department.name)).all()


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(body: DepartmentIn, db: DbSession, user: Allow(AD)):
    dept = master_service.create_department(db, user, name=body.name, monthly_budget=body.monthly_budget)
    db.commit()
    return dept


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def update_department(department_id: int, body: DepartmentUpdate, db: DbSession, user: Allow(AD)):
    dept = _get(db, Department, department_id, "Department")
    master_service.update_department(db, user, dept, name=body.name, monthly_budget=body.monthly_budget)
    db.commit()
    return dept


# ---- users ----------------------------------------------------------------------------------------


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: DbSession, _: Allow(AD), role: Role | None = None, department_id: int | None = None,
               active: bool | None = None, q: Annotated[str | None, Query(description="Name or email")] = None):
    stmt = select(User).options(selectinload(User.department)).order_by(User.name)
    if role:
        stmt = stmt.where(User.role == role)
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    if q:
        stmt = stmt.where(or_(func.lower(User.name).contains(q.lower()), func.lower(User.email).contains(q.lower())))
    return db.scalars(stmt).all()


@router.post("/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, user: Allow(AD)):
    created = master_service.create_user(db, user, name=body.name, email=body.email, password=body.password,
                                         role=body.role, department_id=body.department_id)
    db.commit()
    return created


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, body: UserUpdate, db: DbSession, user: Allow(AD)):
    target = _get(db, User, user_id, "User")
    changes = body.model_dump(exclude_unset=True)
    master_service.update_user(db, user, target, **changes)
    db.commit()
    return target


# ---- suppliers ------------------------------------------------------------------------------------


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: DbSession, _: Allow(P, A, F, AD), active: bool | None = None, q: str | None = None):
    stmt = select(Supplier).order_by(Supplier.name)
    if active is not None:
        stmt = stmt.where(Supplier.is_active.is_(active))
    if q:
        stmt = stmt.where(func.lower(Supplier.name).contains(q.lower()))
    return db.scalars(stmt).all()


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierIn, db: DbSession, user: Allow(AD)):
    supplier = master_service.create_supplier(db, user, **body.model_dump())
    db.commit()
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierUpdate, db: DbSession, user: Allow(AD)):
    supplier = _get(db, Supplier, supplier_id, "Supplier")
    master_service.update_supplier(db, user, supplier, **body.model_dump(exclude_unset=True))
    db.commit()
    return supplier


# ---- items ----------------------------------------------------------------------------------------


@router.get("/items", response_model=list[ItemOut])
def list_items(db: DbSession, _: Allow(*READ_ROLES), category: str | None = None, q: str | None = None):
    stmt = select(Item).order_by(Item.category, Item.name)
    if category:
        stmt = stmt.where(Item.category == category)
    if q:
        stmt = stmt.where(func.lower(Item.name).contains(q.lower()))
    return db.scalars(stmt).all()


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, db: DbSession, user: Allow(AD)):
    item = master_service.create_item(db, user, **body.model_dump())
    db.commit()
    return item


@router.patch("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemUpdate, db: DbSession, user: Allow(AD)):
    item = _get(db, Item, item_id, "Item")
    master_service.update_item(db, user, item, **body.model_dump(exclude_unset=True))
    db.commit()
    return item


# ---- settings -------------------------------------------------------------------------------------


@router.get("/settings", response_model=list[SettingOut])
def list_settings(db: DbSession, _: Allow(AD, F)):
    return [SettingOut(key=key, value=value) for key, value in master_service.list_settings(db)]


@router.put("/settings/{key}", response_model=SettingOut)
def put_setting(key: str, body: SettingIn, db: DbSession, user: Allow(AD)):
    setting = master_service.set_setting(db, user, key, body.value)
    db.commit()
    return setting
