"""Helpers shared by the services: role guards, input validation, message formatting."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core import clock
from app.core.errors import BusinessRuleViolation, Forbidden
from app.models.enums import Role
from app.models.master import User

# ---- actors ----------------------------------------------------------------------------------


def ensure_role(actor: User, *roles: Role, to: str) -> None:
    """Refuse unless `actor` is active and holds one of `roles`. `to` completes
    "Only X users can …". ADMIN is never passed here for transactional actions (D-09)."""
    if not actor.is_active:
        raise Forbidden("Your account is deactivated")
    if actor.role not in roles:
        who = " or ".join(r.value for r in roles)
        raise Forbidden(f"Only {who} users can {to}; you are {actor.role}")


# ---- input validation ------------------------------------------------------------------------


class Problems:
    """Collects every validation failure so the user sees them all at once."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def raise_if_any(self) -> None:
        if len(self.items) == 1:
            raise BusinessRuleViolation(self.items[0])
        if self.items:
            raise BusinessRuleViolation("; ".join(self.items), details=self.items)


def require_text(value: str | None, what: str) -> str:
    """Stripped non-empty text, e.g. a mandatory reason. `what` starts the error message."""
    text = (value or "").strip()
    if not text:
        raise BusinessRuleViolation(f"{what} is required")
    return text


def optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def to_decimal(value: Any, what: str, places: int) -> Decimal:
    """Decimal with at most `places` decimals. Floats are refused (D-30)."""
    if isinstance(value, float) or isinstance(value, bool):
        raise BusinessRuleViolation(f"{what} must be a decimal number, not {type(value).__name__}")
    try:
        number = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleViolation(f"{what} must be a number") from None
    if not number.is_finite():
        raise BusinessRuleViolation(f"{what} must be a number")
    if number.as_tuple().exponent < -places and number != number.quantize(Decimal(1).scaleb(-places)):
        raise BusinessRuleViolation(f"{what} can have at most {places} decimal places")
    return number


PAISA = Decimal("0.01")
MILLI = Decimal("0.001")


def money(value: Any, what: str, *, allow_zero: bool = False) -> Decimal:
    """Validated amount, normalised to 2 places (₹10 → 10.00)."""
    number = to_decimal(value, what, 2)
    if number < 0 or (number == 0 and not allow_zero):
        raise BusinessRuleViolation(f"{what} must be greater than 0" if not allow_zero else f"{what} cannot be negative")
    return number.quantize(PAISA)


def quantity(value: Any, what: str, *, allow_zero: bool = False) -> Decimal:
    """Validated quantity, normalised to 3 places."""
    number = to_decimal(value, what, 3)
    if number < 0 or (number == 0 and not allow_zero):
        raise BusinessRuleViolation(f"{what} must be greater than 0" if not allow_zero else f"{what} cannot be negative")
    return number.quantize(MILLI)


def line_amount(qty_: Decimal, unit_price: Decimal) -> Decimal:
    """qty × price rounded to the paisa, half up (D-53). Every total — PR, quotation, PO and the
    invoice-lines sum in the three-way match — is the sum of these, so all agree to the paisa."""
    return (qty_ * unit_price).quantize(PAISA, rounding=ROUND_HALF_UP)


def not_in_future(value: date, what: str) -> date:
    if value > clock.today():
        raise BusinessRuleViolation(f"{what} ({fmt_date(value)}) cannot be in the future")
    return value


# ---- formatting for messages -----------------------------------------------------------------


def inr(amount: Decimal) -> str:
    """₹1,38,000.00 — Indian digit grouping."""
    sign = "-" if amount < 0 else ""
    whole, _, paise = f"{abs(amount):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{paise}"


def qty(value: Decimal) -> str:
    """280.000 → 280, 2.500 → 2.5."""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def fmt_date(value: date) -> str:
    return value.strftime("%d %b %Y")
