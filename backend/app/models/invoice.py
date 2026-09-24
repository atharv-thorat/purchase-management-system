"""Invoice, InvoiceLine, Payment."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.enums import InvoiceStatus, PaymentMode
from app.models.master import Supplier, User
from app.models.purchase_order import POLine, PurchaseOrder
from app.models.types import Money, Quantity, enum_column


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        # Duplicate supplier invoice numbers are blocked, except against REJECTED ones (rule 11, D-03).
        Index(
            "uq_invoice_live_supplier_number",
            "supplier_id",
            "supplier_invoice_number",
            unique=True,
            sqlite_where=text("status <> 'REJECTED'"),
        ),
        CheckConstraint("total >= 0", name="total_non_negative"),
        CheckConstraint(
            "status <> 'REJECTED' OR length(trim(coalesce(rejection_reason, ''))) > 0",
            name="rejection_needs_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_invoice_number: Mapped[str] = mapped_column(String(50))
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"))
    invoice_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Money)  # as printed by the supplier; checked, not computed (D-20)
    status: Mapped[InvoiceStatus] = mapped_column(
        enum_column(InvoiceStatus), default=InvoiceStatus.PENDING_MATCH, index=True
    )
    mismatch_details: Mapped[str | None] = mapped_column(Text)  # one failing check per line
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

    po: Mapped[PurchaseOrder] = relationship(back_populates="invoices")
    supplier: Mapped[Supplier] = relationship()
    creator: Mapped[User] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", order_by="Payment.id")

    def __repr__(self) -> str:
        return f"<Invoice {self.supplier_invoice_number} {self.status}>"


class InvoiceLine(Base):
    __tablename__ = "invoice_line"
    __table_args__ = (
        UniqueConstraint("invoice_id", "po_line_id"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_line.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Quantity)
    unit_price: Mapped[Decimal] = mapped_column(Money)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    po_line: Mapped[POLine] = relationship()


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    mode: Mapped[PaymentMode] = mapped_column(enum_column(PaymentMode))
    reference_no: Mapped[str] = mapped_column(String(100))
    paid_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=now)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
    recorder: Mapped[User] = relationship()
