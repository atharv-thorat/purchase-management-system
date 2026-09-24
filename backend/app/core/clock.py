"""Single source of "now", in server local time (IST).

Datetimes are stored naive, in IST, so the budget check's "current calendar month" (D-05) is a
plain comparison (D-40). Tests and the seed pin the clock with `frozen_at`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

_TZ = ZoneInfo(settings.timezone)
_frozen: datetime | None = None


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    return datetime.now(_TZ).replace(tzinfo=None, microsecond=0)


def today() -> date:
    return now().date()


def month_start(at: datetime | None = None) -> datetime:
    at = at or now()
    return at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(at: datetime | None = None) -> datetime:
    start = month_start(at)
    return (start + timedelta(days=32)).replace(day=1)


def freeze(at: datetime | None) -> None:
    """Pin now() to `at` (naive IST); None unpins."""
    global _frozen
    _frozen = at.replace(microsecond=0) if at else None


@contextmanager
def frozen_at(at: datetime) -> Iterator[None]:
    previous = _frozen
    freeze(at)
    try:
        yield
    finally:
        freeze(previous)
