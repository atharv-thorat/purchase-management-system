"""Counter table behind PR-/PO-/GRN- numbers (D-31). See services/numbering.py."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import DocumentType
from app.models.types import enum_column


class DocumentSequence(Base):
    __tablename__ = "document_sequence"
    __table_args__ = (CheckConstraint("last_value >= 0", name="last_value_non_negative"),)

    doc_type: Mapped[DocumentType] = mapped_column(enum_column(DocumentType), primary_key=True)
    last_value: Mapped[int] = mapped_column(default=0)
