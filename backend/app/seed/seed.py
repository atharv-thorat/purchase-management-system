"""Reset the database and load the demo data (SPEC "Seed data").

    python -m app.seed.seed          # or ./reset_db.sh

Drops every table, recreates the schema and loads masters plus eight PRs that between them
cover every state the demo needs (see SCENARIOS at the bottom). Workflow services don't exist
yet, so the history is written directly — each status change with its AuditLog row and
ApprovalLog entries — and `verify.py` then checks that the result obeys the business rules.

Timestamps are relative to now and squeezed into the current calendar month (SeedClock), so
the budget figures on the dashboard and the over-budget warning on PR-0007 hold whatever
day the demo is seeded.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import MetaData, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    ApprovalLog,
    Department,
    GoodsReceipt,
    GRNLine,
    Invoice,
    InvoiceLine,
    Item,
    Payment,
    POLine,
    PRLine,
    PurchaseOrder,
    PurchaseRequest,
    Quotation,
    QuotationLine,
    Setting,
    Supplier,
    User,
)
from app.models.enums import (
    SETTING_DEFAULTS,
    ApprovalAction,
    ApprovalLevel,
    AuditAction,
    DocumentType,
    EntityType,
    InvoiceStatus,
    ItemUnit,
    PaymentMode,
    POStatus,
    PRStatus,
    Role,
    SettingKey,
)
from app.seed.verify import verify
from app.services.audit_service import record_status_change
from app.services.numbering import next_number

D = Decimal

# --------------------------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------------------------

DEPARTMENTS = [("IT", D("1000000")), ("Operations", D("500000")), ("HR", D("200000"))]

# (name, email, role, department) — 9 users, HR has none (D-24).
USERS = [
    ("Riya Sharma", "requester.it@example.com", Role.REQUESTER, "IT"),
    ("Arjun Mehta", "head.it@example.com", Role.DEPT_HEAD, "IT"),
    ("Karan Patel", "requester.ops@example.com", Role.REQUESTER, "Operations"),
    ("Neha Iyer", "head.ops@example.com", Role.DEPT_HEAD, "Operations"),
    ("Priya Nair", "finance@example.com", Role.FINANCE, None),
    ("Vikram Rao", "purchase@example.com", Role.PURCHASE, None),
    ("Suresh Kumar", "store@example.com", Role.STORE, None),
    ("Anita Desai", "accounts@example.com", Role.ACCOUNTS, None),
    ("Meera Joshi", "admin@example.com", Role.ADMIN, None),
]

# (name, contact, email, phone, gstin)
SUPPLIERS = [
    ("Techno Solutions Pvt Ltd", "Rahul Verma", "sales@technosolutions.example", "+91 22 4012 3456", "27AAACT2727Q1ZW"),
    ("Digital Edge Systems", "Lakshmi Rao", "orders@digitaledge.example", "+91 80 4123 7788", "29AAECD4321M1ZQ"),
    ("Infoline Computers", "Sameer Kulkarni", "quotes@infoline.example", "+91 20 2553 9021", "27AAFCI6012B1Z8"),
    ("Shree Steel & Safety Traders", "Mahesh Jadhav", "shreesteel@example.com", "+91 20 2712 4450", "27AAGFS5678K1Z2"),
    ("Bharat Office Supplies", "Pooja Malhotra", "sales@bharatoffice.example", "+91 11 4155 2090", "07AABCB1234C1Z5"),
]

# (name, unit, category)
ITEMS = [
    ('Laptop 14" (i5, 16 GB, 512 GB SSD)', ItemUnit.PCS, "IT Hardware"),
    ('24" LED Monitor', ItemUnit.PCS, "IT Hardware"),
    ("USB-C Docking Station", ItemUnit.PCS, "IT Hardware"),
    ("Wireless Keyboard", ItemUnit.PCS, "IT Peripherals"),
    ("Wireless Mouse", ItemUnit.PCS, "IT Peripherals"),
    ("Conference Speakerphone", ItemUnit.PCS, "IT Peripherals"),
    ("A4 Copier Paper (5 reams)", ItemUnit.BOX, "Stationery"),
    ("Ballpoint Pens (box of 50)", ItemUnit.BOX, "Stationery"),
    ("MS Steel Rod 12 mm", ItemUnit.KG, "Raw Material"),
    ("Safety Helmet", ItemUnit.PCS, "Safety"),
    ("Hydraulic Pallet Truck", ItemUnit.PCS, "Material Handling"),
    ("Packaging Tape (box of 36)", ItemUnit.BOX, "Packaging"),
]
LAPTOP, MONITOR, DOCK, KEYBOARD, MOUSE, SPEAKERPHONE, PAPER, PENS, STEEL, HELMET, PALLET_TRUCK, TAPE = (
    name for name, _, _ in ITEMS
)


# --------------------------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------------------------


class SeedClock:
    """`at(days_ago)` → a timestamp inside the current calendar month.

    Scenarios span SPAN days. Late in the month that maps 1:1 onto real days; early in the
    month the whole timeline is compressed into the days elapsed so far, keeping the order.
    """

    SPAN = 22

    def __init__(self) -> None:
        self.now = clock.now()
        elapsed = self.now - clock.month_start(self.now)
        self.factor = min(1.0, elapsed / timedelta(days=self.SPAN))

    def at(self, days_ago: float) -> datetime:
        return (self.now - timedelta(days=days_ago) * self.factor).replace(second=0)

    def day(self, days_ago: float) -> date:
        return self.at(days_ago).date()


# --------------------------------------------------------------------------------------------
# Builder: writes one step of history at a time, always with its audit row
# --------------------------------------------------------------------------------------------


@dataclass
class Builder:
    db: Session
    clock: SeedClock
    users: dict[str, User] = field(default_factory=dict)  # by email prefix, e.g. "finance"
    items: dict[str, Item] = field(default_factory=dict)
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    threshold: Decimal = D(SETTING_DEFAULTS[SettingKey.FINANCE_APPROVAL_THRESHOLD])

    def u(self, key: str) -> User:
        return self.users[key]

    def _audit(self, entity_type, obj, action, from_status, to_status, user, at, details=None):
        self.db.flush()  # obj.id
        record_status_change(
            self.db,
            entity_type=entity_type,
            entity_id=obj.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            user=user,
            details=details,
            at=at,
        )

    def _move(self, entity_type, obj, action, to_status, user, at, details=None):
        from_status = obj.status
        obj.status = to_status
        obj.updated_at = at
        self._audit(entity_type, obj, action, from_status, to_status, user, at, details)

    # ---- purchase requests --------------------------------------------------------------

    def create_pr(self, requester: User, lines, justification: str, need_in_days: int, days_ago: float):
        at = self.clock.at(days_ago)
        pr = PurchaseRequest(
            pr_number=next_number(self.db, DocumentType.PR),
            requester=requester,
            department=requester.department,
            justification=justification,
            required_by=at.date() + timedelta(days=need_in_days),
            status=PRStatus.DRAFT,
            created_at=at,
            updated_at=at,
        )
        for item_name, qty, price in lines:
            pr.lines.append(PRLine(item=self.items[item_name], quantity=D(qty), estimated_unit_price=D(price)))
        pr.estimated_total = sum((ln.quantity * ln.estimated_unit_price for ln in pr.lines), D("0"))
        self.db.add(pr)
        self._audit(EntityType.PURCHASE_REQUEST, pr, AuditAction.CREATED, None, PRStatus.DRAFT, requester, at)
        return pr

    def submit(self, pr: PurchaseRequest, days_ago: float):
        at = self.clock.at(days_ago)
        # D-01: a dept head's own PR skips the dept-head level.
        to = PRStatus.PENDING_FINANCE if pr.requester.role is Role.DEPT_HEAD else PRStatus.PENDING_DEPT_HEAD
        pr.submitted_at = at
        self._move(EntityType.PURCHASE_REQUEST, pr, AuditAction.SUBMITTED, to, pr.requester, at)

    def approve(self, pr: PurchaseRequest, approver: User, days_ago: float, comment: str | None = None):
        at = self.clock.at(days_ago)
        if pr.status is PRStatus.PENDING_DEPT_HEAD:
            level = ApprovalLevel.DEPT_HEAD
            to = PRStatus.PENDING_FINANCE if pr.estimated_total > self.threshold else PRStatus.APPROVED
        else:
            level, to = ApprovalLevel.FINANCE, PRStatus.APPROVED
        pr.approval_logs.append(
            ApprovalLog(
                level=level, approver=approver, action=ApprovalAction.APPROVED, comment=comment, over_budget=False, at=at
            )
        )
        if to is PRStatus.APPROVED:
            pr.final_approved_at = at
        self._move(EntityType.PURCHASE_REQUEST, pr, AuditAction.APPROVED, to, approver, at, {"level": level.value})

    def reject(self, pr: PurchaseRequest, approver: User, days_ago: float, comment: str):
        at = self.clock.at(days_ago)
        level = ApprovalLevel.DEPT_HEAD if pr.status is PRStatus.PENDING_DEPT_HEAD else ApprovalLevel.FINANCE
        pr.approval_logs.append(
            ApprovalLog(level=level, approver=approver, action=ApprovalAction.REJECTED, comment=comment, at=at)
        )
        pr.rejection_reason = comment
        self._move(
            EntityType.PURCHASE_REQUEST, pr, AuditAction.REJECTED, PRStatus.REJECTED, approver, at,
            {"level": level.value, "comment": comment},
        )

    # ---- quotations and purchase orders -------------------------------------------------

    def quote(self, pr, supplier_key, prices: dict[str, str], days_ago, delivery_days, payment_terms, valid_days=30):
        quote_date = self.clock.day(days_ago)
        q = Quotation(
            pr=pr,
            supplier=self.suppliers[supplier_key],
            quote_date=quote_date,
            valid_until=quote_date + timedelta(days=valid_days),
            delivery_days=delivery_days,
            payment_terms=payment_terms,
            created_by=self.u("purchase").id,
            created_at=self.clock.at(days_ago),
        )
        for pr_line in pr.lines:
            q.lines.append(QuotationLine(pr_line=pr_line, unit_price=D(prices[pr_line.item.name])))
        q.total = sum((ql.unit_price * ql.pr_line.quantity for ql in q.lines), D("0"))
        self.db.add(q)
        return q

    def create_po(self, pr, quotation: Quotation, days_ago, *, selection_reason=None, single_quote_justification=None):
        at = self.clock.at(days_ago)
        buyer = self.u("purchase")
        quotation.is_selected = True
        po = PurchaseOrder(
            po_number=next_number(self.db, DocumentType.PO),
            pr=pr,
            quotation=quotation,
            supplier=quotation.supplier,
            status=POStatus.ISSUED,
            selection_reason=selection_reason,
            single_quote_justification=single_quote_justification,
            created_by=buyer.id,
            created_at=at,
            updated_at=at,
        )
        for ql in quotation.lines:  # price snapshot (rule 7)
            po.lines.append(POLine(item=ql.pr_line.item, qty_ordered=ql.pr_line.quantity, unit_price=ql.unit_price))
        po.total = sum((pl.qty_ordered * pl.unit_price for pl in po.lines), D("0"))
        self.db.add(po)
        self._audit(
            EntityType.PURCHASE_ORDER, po, AuditAction.ISSUED, None, POStatus.ISSUED, buyer, at,
            {"pr_number": pr.pr_number, "supplier": quotation.supplier.name},
        )
        self._move(
            EntityType.PURCHASE_REQUEST, pr, AuditAction.PO_CREATED, PRStatus.PO_CREATED, buyer, at,
            {"po_number": po.po_number},
        )
        return po

    def _po_line(self, po: PurchaseOrder, item_name: str) -> POLine:
        return next(pl for pl in po.lines if pl.item.name == item_name)

    def receive(self, po: PurchaseOrder, days_ago, lines: dict[str, tuple], remarks=None):
        """lines: item name → (received, accepted, rejected, rejection_reason)."""
        at = self.clock.at(days_ago)
        store = self.u("store")
        grn = GoodsReceipt(
            grn_number=next_number(self.db, DocumentType.GRN),
            po=po,
            received_by=store.id,
            received_date=at.date(),
            remarks=remarks,
            created_at=at,
        )
        for item_name, (received, accepted, rejected, reason) in lines.items():
            pl = self._po_line(po, item_name)
            grn.lines.append(
                GRNLine(
                    po_line=pl, qty_received=D(received), qty_accepted=D(accepted), qty_rejected=D(rejected),
                    rejection_reason=reason,
                )
            )
            pl.qty_accepted += D(accepted)
        self.db.add(grn)
        # Receipt status follows accepted quantity (D-18).
        if all(pl.qty_accepted == pl.qty_ordered for pl in po.lines):
            to = POStatus.FULLY_RECEIVED
        elif any(pl.qty_accepted > 0 for pl in po.lines):
            to = POStatus.PARTIALLY_RECEIVED
        else:
            to = POStatus.ISSUED
        self._move(
            EntityType.PURCHASE_ORDER, po, AuditAction.GRN_RECORDED, to, store, at, {"grn_number": grn.grn_number}
        )
        return grn

    def short_close(self, po: PurchaseOrder, days_ago, reason: str):
        at = self.clock.at(days_ago)
        po.short_close_reason = reason
        self._move(
            EntityType.PURCHASE_ORDER, po, AuditAction.SHORT_CLOSED, POStatus.SHORT_CLOSED, self.u("purchase"), at,
            {"reason": reason},
        )

    # ---- invoices and payments ----------------------------------------------------------

    def invoice(self, po: PurchaseOrder, number: str, days_ago, lines: dict[str, tuple], total: str,
                mismatches: list[str] | None = None):
        """lines: item name → (qty, unit_price). `mismatches` given → MISMATCH, else MATCHED."""
        at = self.clock.at(days_ago)
        accounts = self.u("accounts")
        inv = Invoice(
            supplier_invoice_number=number,
            po=po,
            supplier=po.supplier,
            invoice_date=self.clock.day(days_ago + 1),  # dated a day before entry
            total=D(total),
            status=InvoiceStatus.PENDING_MATCH,
            created_by=accounts.id,
            created_at=at,
            updated_at=at,
        )
        for item_name, (qty, price) in lines.items():
            inv.lines.append(InvoiceLine(po_line=self._po_line(po, item_name), qty=D(qty), unit_price=D(price)))
        self.db.add(inv)
        self._audit(EntityType.INVOICE, inv, AuditAction.ENTERED, None, InvoiceStatus.PENDING_MATCH, accounts, at,
                    {"po_number": po.po_number})
        # PENDING_MATCH is transient but both hops are audited (D-35).
        if mismatches:
            inv.mismatch_details = "\n".join(mismatches)
            self._move(EntityType.INVOICE, inv, AuditAction.MISMATCHED, InvoiceStatus.MISMATCH, accounts, at,
                       {"mismatches": mismatches})
        else:
            for il in inv.lines:  # only MATCHED invoices count (D-04)
                il.po_line.qty_invoiced += il.qty
            self._move(EntityType.INVOICE, inv, AuditAction.MATCHED, InvoiceStatus.MATCHED, accounts, at)
        return inv

    def reject_invoice(self, inv: Invoice, days_ago, reason: str):
        at = self.clock.at(days_ago)
        inv.rejection_reason = reason
        self._move(EntityType.INVOICE, inv, AuditAction.REJECTED, InvoiceStatus.REJECTED, self.u("accounts"), at,
                   {"reason": reason})

    def pay(self, inv: Invoice, days_ago, amount: str, mode: PaymentMode, reference_no: str):
        at = self.clock.at(days_ago)
        accounts = self.u("accounts")
        inv.payments.append(
            Payment(amount=D(amount), mode=mode, reference_no=reference_no, paid_on=at.date(),
                    recorded_by=accounts.id, created_at=at)
        )
        paid = sum((p.amount for p in inv.payments), D("0"))
        to = InvoiceStatus.PAID if paid == inv.total else InvoiceStatus.PARTIALLY_PAID
        self._move(EntityType.INVOICE, inv, AuditAction.PAYMENT_RECORDED, to, accounts, at,
                   {"amount": amount, "mode": mode.value, "reference_no": reference_no, "balance": str(inv.total - paid)})

    def close_po(self, po: PurchaseOrder, days_ago):
        """Auto-close after the last payment (rule 14); attributed to whoever paid."""
        self._move(EntityType.PURCHASE_ORDER, po, AuditAction.CLOSED, POStatus.CLOSED, self.u("accounts"),
                   self.clock.at(days_ago), {"auto": True})


# --------------------------------------------------------------------------------------------
# Scenarios, oldest first so document numbers follow the timeline
# --------------------------------------------------------------------------------------------


def scenario_closed_po(b: Builder):
    """PR-0001 / PO-0001: fully received, invoiced, paid → CLOSED. Low value, dept head only."""
    pr = b.create_pr(b.u("requester.it"), [(KEYBOARD, "10", "1500"), (MOUSE, "10", "800")],
                     "Replacement keyboards and mice for the new support desk bay.", 21, 21.8)
    b.submit(pr, 21.7)
    b.approve(pr, b.u("head.it"), 20.9, "OK, within team budget.")
    infoline = b.quote(pr, "Infoline Computers", {KEYBOARD: "1400", MOUSE: "750"}, 19.8, 5, "30 days from invoice")
    b.quote(pr, "Techno Solutions Pvt Ltd", {KEYBOARD: "1450", MOUSE: "800"}, 19.7, 3, "30 days from invoice")
    po = b.create_po(pr, infoline, 18.9)
    b.receive(po, 15.8, {KEYBOARD: ("10", "10", "0", None), MOUSE: ("10", "10", "0", None)})
    inv = b.invoice(po, "INF/2026/0412", 13.8, {KEYBOARD: ("10", "1400"), MOUSE: ("10", "750")}, "21500")
    b.pay(inv, 10.8, "21500", PaymentMode.NEFT, "HDFCN52026091100418")
    b.close_po(po, 10.8)


def scenario_short_closed_po(b: Builder):
    """PR-0002 / PO-0002: above threshold (dept head + finance), partly delivered then
    SHORT_CLOSED. First invoice billed at list price → MISMATCH → REJECTED; the corrected invoice
    reuses the number (D-03), is MATCHED and part-paid. Paying the ₹38,000 balance closes the PO."""
    pr = b.create_pr(b.u("requester.it"), [(MONITOR, "20", "12000")],
                     "Dual-monitor setup for the analytics team (20 seats).", 25, 20.8)
    b.submit(pr, 20.7)
    b.approve(pr, b.u("head.it"), 19.9)
    b.approve(pr, b.u("finance"), 19.2, "Approved against Q3 IT capex.")
    techno = b.quote(pr, "Techno Solutions Pvt Ltd", {MONITOR: "11500"}, 17.9, 7, "45 days from invoice")
    b.quote(pr, "Digital Edge Systems", {MONITOR: "11800"}, 17.8, 10, "30 days from invoice")
    po = b.create_po(pr, techno, 16.9)
    b.receive(po, 12.8, {MONITOR: ("12", "12", "0", None)}, remarks="Supplier short-shipped; balance promised next week.")
    wrong = b.invoice(po, "TSPL/2026/1187", 9.8, {MONITOR: ("12", "12000")}, "144000",
                      mismatches=[f"{MONITOR}: unit price ₹12,000.00 does not match PO price ₹11,500.00"])
    b.short_close(po, 8.8, "Supplier has discontinued this model; the remaining 8 units will be raised on a new PR.")
    b.reject_invoice(wrong, 7.9, "Billed at list price instead of the PO price. Supplier to reissue at ₹11,500.")
    corrected = b.invoice(po, "TSPL/2026/1187", 5.8, {MONITOR: ("12", "11500")}, "138000")
    b.pay(corrected, 2.9, "100000", PaymentMode.NEFT, "ICICN52026092000731")


def scenario_partial_po_with_mismatch(b: Builder):
    """PR-0003 / PO-0003: single quote with justification; partial GRN with rejected steel;
    supplier invoiced the rejected kilos too → MISMATCH (rematch/reject demo)."""
    pr = b.create_pr(b.u("requester.ops"), [(STEEL, "500", "90"), (HELMET, "20", "600")],
                     "Steel for mezzanine racking in Warehouse B, plus helmets for the install crew.", 20, 16.8)
    b.submit(pr, 16.7)
    b.approve(pr, b.u("head.ops"), 15.9)
    b.approve(pr, b.u("finance"), 14.9)
    shree = b.quote(pr, "Shree Steel & Safety Traders", {STEEL: "88", HELMET: "550"}, 13.9, 4, "15 days from invoice")
    po = b.create_po(pr, shree, 12.9,
                     single_quote_justification="Only BIS-certified IS 2062 steel stockist that delivers to our Pune site "
                                                "within a week; two other vendors declined to quote.")
    b.receive(po, 9.8, {STEEL: ("300", "280", "20", "Surface rust on 20 kg"), HELMET: ("20", "20", "0", None)},
              remarks="First lot of steel; balance 200 kg due next week.")
    b.invoice(po, "SSST/26-27/0923", 6.9, {STEEL: ("300", "88"), HELMET: ("20", "550")}, "37400",
              mismatches=[f"{STEEL}: invoiced 300 kg but only 280 kg accepted (0 kg already invoiced)"])


def scenario_rejected_pr(b: Builder):
    """PR-0004: rejected by the dept head, ready to edit and resubmit."""
    pr = b.create_pr(b.u("requester.ops"), [(PAPER, "40", "260"), (PENS, "10", "350")],
                     "Quarterly stationery for the dispatch office.", 14, 11.8)
    b.submit(pr, 11.7)
    b.reject(pr, b.u("head.ops"), 10.9, "Store still has 25 boxes of A4 paper. Reduce the paper quantity and resubmit.")


def scenario_approved_pr_with_three_quotes(b: Builder):
    """PR-0005: APPROVED with 3 quotes. Infoline is cheapest overall but slowest; laptop is
    cheapest at Infoline, docking station at Techno — picking anyone but Infoline needs a reason."""
    pr = b.create_pr(b.u("requester.it"), [(LAPTOP, "5", "72000"), (DOCK, "5", "9000")],
                     "Laptops and docks for five new data-engineering hires joining next month.", 30, 8.8)
    b.submit(pr, 8.7)
    b.approve(pr, b.u("head.it"), 7.9, "Headcount approved in the Q3 plan.")
    b.approve(pr, b.u("finance"), 6.9)
    b.quote(pr, "Techno Solutions Pvt Ltd", {LAPTOP: "69500", DOCK: "8200"}, 4.9, 7, "30 days from invoice")
    b.quote(pr, "Digital Edge Systems", {LAPTOP: "68900", DOCK: "9100"}, 4.8, 5, "45 days from invoice")
    b.quote(pr, "Infoline Computers", {LAPTOP: "67800", DOCK: "9400"}, 3.9, 21, "50% advance, 50% on delivery")


def scenario_dept_head_pr(b: Builder):
    """PR-0006: raised by the IT dept head, below threshold, yet waiting on FINANCE (D-01)."""
    pr = b.create_pr(b.u("head.it"), [(SPEAKERPHONE, "2", "18500")],
                     "Speakerphones for the two new meeting rooms on the 4th floor.", 15, 5.8)
    b.submit(pr, 5.7)


def scenario_pending_over_budget(b: Builder):
    """PR-0007: waiting on the Operations dept head. Operations has ₹55,000 committed this
    month (PO-0003); ₹4,49,000 more exceeds the ₹5,00,000 budget → over-budget warning."""
    pr = b.create_pr(b.u("requester.ops"), [(PALLET_TRUCK, "10", "42000"), (TAPE, "20", "1450")],
                     "Material handling for the Bay 3 go-live.", 21, 2.8)
    b.submit(pr, 2.7)


def scenario_draft(b: Builder):
    """PR-0008: an unsubmitted draft."""
    b.create_pr(b.u("requester.it"), [(PAPER, "10", "260")], "Printer paper for the IT floor.", 10, 0.9)


SCENARIOS = [
    scenario_closed_po,
    scenario_short_closed_po,
    scenario_partial_po_with_mismatch,
    scenario_rejected_pr,
    scenario_approved_pr_with_three_quotes,
    scenario_dept_head_pr,
    scenario_pending_over_budget,
    scenario_draft,
]


# --------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------


def reset_schema() -> None:
    """Drop every table (including ones no longer in the models) and recreate the schema."""
    existing = MetaData()
    existing.reflect(engine)
    existing.drop_all(engine)
    Base.metadata.create_all(engine)


def seed_masters(db: Session, b: Builder) -> None:
    for key, value in SETTING_DEFAULTS.items():
        db.add(Setting(key=key.value, value=value))
    departments = {name: Department(name=name, monthly_budget=budget) for name, budget in DEPARTMENTS}
    db.add_all(departments.values())

    password_hash = hash_password(settings.demo_password)  # one hash is enough for demo accounts
    for name, email, role, dept in USERS:
        user = User(name=name, email=email, password_hash=password_hash, role=role,
                    department=departments[dept] if dept else None, is_active=True)
        db.add(user)
        b.users[email.split("@")[0]] = user
    for name, contact, email, phone, gstin in SUPPLIERS:
        b.suppliers[name] = Supplier(name=name, contact_person=contact, email=email, phone=phone, gstin=gstin)
    for name, unit, category in ITEMS:
        b.items[name] = Item(name=name, unit=unit, category=category)
    db.add_all([*b.suppliers.values(), *b.items.values()])
    db.flush()


def seed(db: Session) -> None:
    b = Builder(db, SeedClock())
    seed_masters(db, b)
    for scenario in SCENARIOS:
        scenario(b)
    db.flush()
    problems = verify(db)
    if problems:
        raise RuntimeError("Seed data is inconsistent:\n  - " + "\n  - ".join(problems))


def summary(db: Session) -> str:
    rows = [f"{pr.pr_number}  {pr.status:<17} {pr.department.name:<10} ₹{pr.estimated_total:>12,.2f}  "
            + ", ".join(f"{po.po_number} {po.status}" for po in pr.purchase_orders)
            for pr in db.scalars(select(PurchaseRequest).order_by(PurchaseRequest.id))]
    invoices = [f"{inv.supplier_invoice_number:<16} {inv.po.po_number}  {inv.status}"
                for inv in db.scalars(select(Invoice).order_by(Invoice.id))]
    return "\n".join(["Purchase requests:", *("  " + r for r in rows), "Invoices:", *("  " + i for i in invoices)])


def main() -> None:
    reset_schema()
    with SessionLocal() as db:
        seed(db)
        db.commit()
        print(f"Database reset and seeded ({engine.url}).")
        print(summary(db))
        print(f"\nDemo users (password '{settings.demo_password}'):")
        for u in db.scalars(select(User).order_by(User.id)):
            print(f"  {u.role:<10} {u.email:<28} {u.name}" + (f" ({u.department.name})" if u.department else ""))


if __name__ == "__main__":
    main()
