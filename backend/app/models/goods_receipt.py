"""GoodsReceipt, GRNLine."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.master import User
from app.models.purchase_order import POLine, PurchaseOrder
from app.models.types import Quantity


class GoodsReceipt(Base):
    __tablename__ = "goods_receipt"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(20), unique=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id"), index=True)
    received_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    received_date: Mapped[date] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)

    po: Mapped[PurchaseOrder] = relationship(back_populates="goods_receipts")
    receiver: Mapped[User] = relationship()
    lines: Mapped[list["GRNLine"]] = relationship(
        back_populates="grn", cascade="all, delete-orphan", order_by="GRNLine.id"
    )


class GRNLine(Base):
    __tablename__ = "grn_line"
    __table_args__ = (
        UniqueConstraint("grn_id", "po_line_id"),
        CheckConstraint(
            "qty_received >= 0 AND qty_accepted >= 0 AND qty_rejected >= 0", name="quantities_non_negative"
        ),
        # Exact because quantities are scaled integers (D-38).
        CheckConstraint("qty_accepted + qty_rejected = qty_received", name="accepted_plus_rejected"),
        CheckConstraint(
            "qty_rejected = 0 OR length(trim(coalesce(rejection_reason, ''))) > 0",
            name="rejection_needs_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("goods_receipt.id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_line.id"), index=True)
    qty_received: Mapped[Decimal] = mapped_column(Quantity)
    qty_accepted: Mapped[Decimal] = mapped_column(Quantity)
    qty_rejected: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    grn: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    po_line: Mapped[POLine] = relationship()
