"""Importing this package registers every table on Base.metadata."""

from app.models.audit import AuditLog
from app.models.goods_receipt import GoodsReceipt, GRNLine
from app.models.invoice import Invoice, InvoiceLine, Payment
from app.models.master import Department, Item, Setting, Supplier, User
from app.models.purchase_order import POLine, PurchaseOrder
from app.models.purchase_request import ApprovalLog, PRLine, PurchaseRequest
from app.models.quotation import Quotation, QuotationLine
from app.models.sequence import DocumentSequence

__all__ = [
    "ApprovalLog",
    "AuditLog",
    "Department",
    "DocumentSequence",
    "GRNLine",
    "GoodsReceipt",
    "Invoice",
    "InvoiceLine",
    "Item",
    "POLine",
    "PRLine",
    "Payment",
    "PurchaseOrder",
    "PurchaseRequest",
    "Quotation",
    "QuotationLine",
    "Setting",
    "Supplier",
    "User",
]
