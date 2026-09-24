"""Every status, role and code the system uses. Stored as their string values."""

from enum import StrEnum


class Role(StrEnum):
    REQUESTER = "REQUESTER"
    DEPT_HEAD = "DEPT_HEAD"
    FINANCE = "FINANCE"
    PURCHASE = "PURCHASE"
    STORE = "STORE"
    ACCOUNTS = "ACCOUNTS"
    ADMIN = "ADMIN"


# Only these roles belong to a department and raise PRs (D-19, D-01).
DEPARTMENT_ROLES = frozenset({Role.REQUESTER, Role.DEPT_HEAD})


class PRStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_DEPT_HEAD = "PENDING_DEPT_HEAD"
    PENDING_FINANCE = "PENDING_FINANCE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PO_CREATED = "PO_CREATED"


class POStatus(StrEnum):
    ISSUED = "ISSUED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    FULLY_RECEIVED = "FULLY_RECEIVED"
    SHORT_CLOSED = "SHORT_CLOSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(StrEnum):
    PENDING_MATCH = "PENDING_MATCH"
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    REJECTED = "REJECTED"


# Invoices that passed the three-way match; only these count toward po_line.qty_invoiced (D-04).
MATCHED_INVOICE_STATUSES = frozenset(
    {InvoiceStatus.MATCHED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID}
)


class PaymentMode(StrEnum):
    NEFT = "NEFT"
    CHEQUE = "CHEQUE"
    UPI = "UPI"


class ItemUnit(StrEnum):
    PCS = "pcs"
    KG = "kg"
    BOX = "box"


class ApprovalLevel(StrEnum):
    DEPT_HEAD = "DEPT_HEAD"
    FINANCE = "FINANCE"


class ApprovalAction(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DocumentType(StrEnum):
    """Prefixes of system-generated document numbers (D-31)."""

    PR = "PR"
    PO = "PO"
    GRN = "GRN"


class EntityType(StrEnum):
    PURCHASE_REQUEST = "PURCHASE_REQUEST"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    INVOICE = "INVOICE"


class AuditAction(StrEnum):
    # purchase request
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    RESUBMITTED = "RESUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PO_CREATED = "PO_CREATED"
    PO_CANCELLED = "PO_CANCELLED"
    # purchase order
    ISSUED = "ISSUED"
    GRN_RECORDED = "GRN_RECORDED"
    CANCELLED = "CANCELLED"
    SHORT_CLOSED = "SHORT_CLOSED"
    CLOSED = "CLOSED"
    # invoice
    ENTERED = "ENTERED"
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    REMATCH_REQUESTED = "REMATCH_REQUESTED"
    PAYMENT_RECORDED = "PAYMENT_RECORDED"


class SettingKey(StrEnum):
    FINANCE_APPROVAL_THRESHOLD = "FINANCE_APPROVAL_THRESHOLD"


SETTING_DEFAULTS: dict[SettingKey, str] = {
    SettingKey.FINANCE_APPROVAL_THRESHOLD: "50000",
}
