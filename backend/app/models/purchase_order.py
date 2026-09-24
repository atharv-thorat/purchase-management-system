"""PurchaseOrder, POLine."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.enums import POStatus
from app.models.master import Item, Supplier, User
from app.models.purchase_request import PurchaseRequest
from app.models.quotation import Quotation
from app.models.types import Money, Quantity, enum_column

if TYPE_CHECKING:
    from app.models.goods_receipt import GoodsReceipt
    from app.models.invoice import Invoice


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"
    __table_args__ = (
        # One PR -> one PO, counting non-cancelled POs only (D-06, D-32).
        Index(
            "uq_purchase_order_live_per_pr",
            "pr_id",
            unique=True,
            sqlite_where=text("status <> 'CANCELLED'"),
        ),
        CheckConstraint("status <> 'CANCELLED' OR cancel_reason IS NOT NULL", name="cancel_needs_reason"),
        CheckConstraint(
            "status <> 'SHORT_CLOSED' OR short_close_reason IS NOT NULL", name="short_close_needs_reason"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(20), unique=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_request.id"), index=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotation.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    status: Mapped[POStatus] = mapped_column(enum_column(POStatus), default=POStatus.ISSUED, index=True)
    total: Mapped[Decimal] = mapped_column(Money)  # Σ lines (D-29)
    selection_reason: Mapped[str | None] = mapped_column(Text)
    single_quote_justification: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    short_close_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

    pr: Mapped[PurchaseRequest] = relationship(back_populates="purchase_orders")
    quotation: Mapped[Quotation] = relationship()
    supplier: Mapped[Supplier] = relationship()
    creator: Mapped[User] = relationship()
    lines: Mapped[list["POLine"]] = relationship(
        back_populates="po", cascade="all, delete-orphan", order_by="POLine.id"
    )
    goods_receipts: Mapped[list["GoodsReceipt"]] = relationship(back_populates="po", order_by="GoodsReceipt.id")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="po", order_by="Invoice.id")

    def __repr__(self) -> str:
        return f"<PO {self.po_number} {self.status}>"


class POLine(Base):
    __tablename__ = "po_line"
    __table_args__ = (
        CheckConstraint("qty_ordered > 0", name="qty_ordered_positive"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
        # Cumulative counters can never overtake what feeds them (rules 9 and 10).
        CheckConstraint("qty_accepted BETWEEN 0 AND qty_ordered", name="accepted_within_ordered"),
        CheckConstraint("qty_invoiced BETWEEN 0 AND qty_accepted", name="invoiced_within_accepted"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty_ordered: Mapped[Decimal] = mapped_column(Quantity)
    unit_price: Mapped[Decimal] = mapped_column(Money)  # SNAPSHOT of the quotation price; never read live
    qty_accepted: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0.000"))  # Σ GRN accepted
    qty_invoiced: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0.000"))  # Σ MATCHED invoices (D-04)

    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship()
