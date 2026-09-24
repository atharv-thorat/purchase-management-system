"""Column types shared by the models.

Money and quantities are stored as scaled integers (paise, thousandths) and surface in Python
as `Decimal`. SQLite has no decimal type — `Numeric` there is a float underneath — so this is
what makes exact price equality (D-21) and the arithmetic CHECK constraints exact (D-38).
"""

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Enum
from sqlalchemy.types import TypeDecorator


class _ScaledDecimal(TypeDecorator):
    impl = BigInteger
    cache_ok = True
    scale: int = 0

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError(f"{type(self).__name__} values must be Decimal or int, not float")
        scaled = Decimal(value).scaleb(self.scale)
        if scaled != scaled.to_integral_value():
            raise ValueError(f"{value} has more than {self.scale} decimal places")
        return int(scaled)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(int(value)).scaleb(-self.scale)


class Money(_ScaledDecimal):
    """INR, to the paisa."""

    cache_ok = True
    scale = 2


class Quantity(_ScaledDecimal):
    """Up to 3 decimals, enough for kg."""

    cache_ok = True
    scale = 3


def enum_column(enum_cls: type[StrEnum]) -> Enum:
    """String column restricted to the enum's values by a CHECK constraint."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
        length=max(len(m.value) for m in enum_cls),
        name=enum_cls.__name__.lower(),
    )
