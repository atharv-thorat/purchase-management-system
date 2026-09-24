"""Shared router pieces: role-gated actors, pagination, date ranges, documented error responses."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select

from app.core.deps import require_roles
from app.models.enums import Role
from app.models.master import User
from app.schemas.common import ErrorResponse

READ_ROLES = tuple(Role)


def Allow(*roles: Role) -> Any:  # noqa: N802 - reads like a type in signatures
    """`user: Allow(Role.PURCHASE)` — the current user, refused with 403 unless in `roles`."""
    return Annotated[User, Depends(require_roles(*roles))]


@dataclass
class Paging:
    page: int
    page_size: int


def paging(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paging:
    return Paging(page, page_size)


PagingParams = Annotated[Paging, Depends(paging)]
DateFrom = Annotated[date | None, Query(description="Inclusive start date (YYYY-MM-DD)")]
DateTo = Annotated[date | None, Query(description="Inclusive end date (YYYY-MM-DD)")]


def in_date_range(stmt: Select, column, date_from: date | None, date_to: date | None) -> Select:
    """Filter a date or datetime column to [date_from, date_to], both inclusive."""
    is_datetime = getattr(column.type, "python_type", None) is datetime
    if date_from:
        stmt = stmt.where(column >= (datetime.combine(date_from, time.min) if is_datetime else date_from))
    if date_to:
        stmt = stmt.where(column < datetime.combine(date_to + timedelta(days=1), time.min) if is_datetime
                          else column <= date_to)
    return stmt


def _err(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


# Documented on every router so Swagger shows the shared error shape.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _err("Not logged in or token expired"),
    403: _err("Your role may not do this (segregation of duties)"),
    404: _err("Not found, or outside what you may see"),
    409: _err("Not allowed in the record's current status"),
    422: _err("Business rule violated or invalid input"),
}
