"""Master data: Department, User, Supplier, Item, Setting."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.enums import ItemUnit, Role
from app.models.types import Money, enum_column


class Department(Base):
    __tablename__ = "department"
    __table_args__ = (CheckConstraint("monthly_budget >= 0", name="budget_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    monthly_budget: Mapped[Decimal] = mapped_column(Money)

    users: Mapped[list["User"]] = relationship(back_populates="department")

    def __repr__(self) -> str:
        return f"<Department {self.name}>"


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        # REQUESTER and DEPT_HEAD must have a department; every other role must not (D-19).
        CheckConstraint(
            "(role IN ('REQUESTER', 'DEPT_HEAD')) = (department_id IS NOT NULL)",
            name="department_iff_department_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_column(Role))  # exactly one role per user (D-22)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # D-23
    created_at: Mapped[datetime] = mapped_column(default=now)

    department: Mapped[Department | None] = relationship(back_populates="users")

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"


class Supplier(Base):
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(20))
    gstin: Mapped[str] = mapped_column(String(15), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"


class Item(Base):
    __tablename__ = "item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    unit: Mapped[ItemUnit] = mapped_column(enum_column(ItemUnit))
    category: Mapped[str] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<Item {self.name}>"


class Setting(Base):
    """Key/value configuration. Known keys and defaults: enums.SettingKey / SETTING_DEFAULTS."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
