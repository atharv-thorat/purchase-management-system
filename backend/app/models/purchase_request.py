"""PurchaseRequest, PRLine, ApprovalLog."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base
from app.models.enums import ApprovalAction, ApprovalLevel, PRStatus
from app.models.master import Department, Item, User
from app.models.types import Money, Quantity, enum_column

if TYPE_CHECKING:
    from app.models.purchase_order import PurchaseOrder
    from app.models.quotation import Quotation


class PurchaseRequest(Base):
    __tablename__ = "purchase_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_number: Mapped[str] = mapped_column(String(20), unique=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    justification: Mapped[str] = mapped_column(Text)
    required_by: Mapped[date] = mapped_column(Date)
    status: Mapped[PRStatus] = mapped_column(enum_column(PRStatus), default=PRStatus.DRAFT, index=True)
    estimated_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # Σ lines (D-29)
    rejection_reason: Mapped[str | None] = mapped_column(Text)  # latest rejection comment
    submitted_at: Mapped[datetime | None]  # latest (re)submission
    final_approved_at: Mapped[datetime | None]  # drives the budget month (D-05)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

    requester: Mapped[User] = relationship()
    department: Mapped[Department] = relationship()
    lines: Mapped[list["PRLine"]] = relationship(
        back_populates="pr", cascade="all, delete-orphan", order_by="PRLine.id"
    )
    approval_logs: Mapped[list["ApprovalLog"]] = relationship(
        back_populates="pr", cascade="all, delete-orphan", order_by="ApprovalLog.at"
    )
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="pr", order_by="Quotation.id")
    # 1-to-many only because cancelled POs are kept; at most one is not CANCELLED (D-06).
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="pr", order_by="PurchaseOrder.id"
    )

    def __repr__(self) -> str:
        return f"<PR {self.pr_number} {self.status}>"


class PRLine(Base):
    __tablename__ = "pr_line"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("estimated_unit_price >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_request.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    estimated_unit_price: Mapped[Decimal] = mapped_column(Money)

    pr: Mapped[PurchaseRequest] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship()


class ApprovalLog(Base):
    __tablename__ = "approval_log"
    __table_args__ = (
        CheckConstraint(
            "action <> 'REJECTED' OR length(trim(coalesce(comment, ''))) > 0",
            name="rejection_needs_comment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("purchase_request.id", ondelete="CASCADE"), index=True)
    level: Mapped[ApprovalLevel] = mapped_column(enum_column(ApprovalLevel))
    approver_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    action: Mapped[ApprovalAction] = mapped_column(enum_column(ApprovalAction))
    comment: Mapped[str | None] = mapped_column(Text)
    over_budget: Mapped[bool] = mapped_column(Boolean, default=False)  # as the approver saw it (D-36)
    at: Mapped[datetime] = mapped_column(default=now)

    pr: Mapped[PurchaseRequest] = relationship(back_populates="approval_logs")
    approver: Mapped[User] = relationship()
