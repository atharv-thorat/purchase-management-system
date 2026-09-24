"""Shared request/response pieces. Money and quantities are serialised as decimal strings
("21500.00") so no precision is lost in JSON; the frontend formats them."""

from datetime import datetime
from math import ceil
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuditAction, EntityType, ItemUnit, Role

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRef(ORM):
    id: int
    name: str
    role: Role


class DepartmentRef(ORM):
    id: int
    name: str


class SupplierRef(ORM):
    id: int
    name: str


class ItemRef(ORM):
    id: int
    name: str
    unit: ItemUnit
    category: str


class TimelineEntry(BaseModel):
    at: datetime
    entity_type: EntityType
    entity_id: int
    reference: str | None = Field(description="PR / PO / invoice number the row is about")
    action: AuditAction
    from_status: str | None
    to_status: str | None
    user: UserRef | None
    details: dict[str, Any] | None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def of(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size))


class ErrorResponse(BaseModel):
    error: str = Field(examples=["INVALID_TRANSITION"])
    message: str = Field(examples=["Cannot approve purchase request PR-0001: it is DRAFT"])
    details: Any = None


class ReasonIn(BaseModel):
    reason: str


class CommentIn(BaseModel):
    comment: str | None = None


class RequiredCommentIn(BaseModel):
    comment: str
