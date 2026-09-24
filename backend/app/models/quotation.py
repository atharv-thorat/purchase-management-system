"""Quotation, QuotationLine."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.master import Supplier
from app.models.purchase_request import PRLine, PurchaseRequest
from app.models.types import Money


class Quotation(Base):
    __tablename__ = "quotation"
    __table_args__ = (
        UniqueConstraint("pr_id", "supplier_id"),  # one quotation per supplier per PR (D-16)
        # At most one selected quotation per PR.
        Index(
            "uq_quotation_selected_per_pr",
            "pr_id",
            unique=True,
            sqlite_where=text("is_selected = 1"),
        ),
        CheckConstraint("valid_until >= quote_date", name="valid_after_quote_date"),
        CheckConstraint("delivery_days >= 0", name="delivery_days_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_request.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"))
    quote_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    delivery_days: Mapped[int]
    payment_terms: Mapped[str] = mapped_column(String(200))
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # Σ unit_price × PR qty (D-15)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=now)

    pr: Mapped[PurchaseRequest] = relationship(back_populates="quotations")
    supplier: Mapped[Supplier] = relationship()
    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationLine.id"
    )


class QuotationLine(Base):
    __tablename__ = "quotation_line"
    __table_args__ = (
        UniqueConstraint("quotation_id", "pr_line_id"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotation.id", ondelete="CASCADE"), index=True)
    pr_line_id: Mapped[int] = mapped_column(ForeignKey("pr_line.id"))
    unit_price: Mapped[Decimal] = mapped_column(Money)

    quotation: Mapped[Quotation] = relationship(back_populates="lines")
    pr_line: Mapped[PRLine] = relationship()
