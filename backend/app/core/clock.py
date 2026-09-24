"""Single source of "now", in server local time (IST).

Datetimes are stored naive, in IST, so the budget check's "current calendar month" (D-05) is a
plain comparison. Tests monkeypatch `now` to pin the clock.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

_TZ = ZoneInfo(settings.timezone)


def now() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None, microsecond=0)


def today() -> date:
    return now().date()


def month_start(at: datetime | None = None) -> datetime:
    at = at or now()
    return at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
