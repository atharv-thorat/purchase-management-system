"""Reset the database and load the demo data (SPEC "Seed data").

    python -m app.seed.seed              # reset + seed (or ./reset_db.sh, or ./dev.sh --reset)
    python -m app.seed.seed --if-empty   # seed only if there's no data yet (what run.sh does)

Drops every table, recreates the schema, then builds everything through the service layer:
master data via master_service (only the demo users are inserted directly — someone has to
exist to act), and eight PRs whose history is produced by the same service calls the API will
make. Each step runs with the clock pinned to that step's moment, so timestamps, audit rows
and document numbers come out in order. `verify.py` then re-checks the SPEC invariants over
the result and the seed refuses to commit if anything is off (D-41, D-49).

Timestamps are relative to now and squeezed into the current calendar month (SeedClock), so
the budget figures and the over-budget warning on PR-0007 hold whatever day the seed runs.
"""

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, MetaData, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import Invoice, Item, PurchaseOrder, PurchaseRequest, Supplier, User
from app.models.enums import SETTING_DEFAULTS, ItemUnit, PaymentMode, Role
from app.seed.verify import verify
from app.services import (
    grn_service,
    invoice_service,
    master_service,
    payment_service,
    po_service,
    pr_service,
    quotation_service,
)
from app.services.grn_service import GRNLineIn
from app.services.invoice_service import InvoiceLineIn
from app.services.pr_service import PRLineIn
from app.services.quotation_service import QuoteLineIn

# --------------------------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------------------------

DEPARTMENTS = [("IT", "1000000"), ("Operations", "500000"), ("HR", "200000")]

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
# Clock and lookups
# --------------------------------------------------------------------------------------------


class SeedClock:
    """`at(days_ago)` → a timestamp inside the current calendar month.

    Scenarios span SPAN days. Late in the month that maps 1:1 onto real days; early in the
    month the whole timeline is compressed into the days elapsed so far, keeping the order.
    """

    SPAN = 22

    def __init__(self, now: datetime | None = None) -> None:
        self.now = now or clock.now()
        elapsed = self.now - clock.month_start(self.now)
        self.factor = min(1.0, elapsed / timedelta(days=self.SPAN))

    def at(self, days_ago: float) -> datetime:
        return (self.now - timedelta(days=days_ago) * self.factor).replace(second=0)


@dataclass
class Demo:
    """What the scenarios need: the session, actors by email prefix, masters by name."""

    db: Session
    clock: SeedClock
    users: dict[str, User] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    suppliers: dict[str, Supplier] = field(default_factory=dict)

    def u(self, key: str) -> User:
        return self.users[key]

    def at(self, days_ago: float) -> date:
        """Pin the clock to this step; returns that day."""
        clock.freeze(self.clock.at(days_ago))
        return clock.today()

    def pr_lines(self, *lines: tuple[str, str, str]) -> list[PRLineIn]:
        return [PRLineIn(self.items[name].id, q, price) for name, q, price in lines]

    @staticmethod
    def quote_lines(pr: PurchaseRequest, prices: dict[str, str]) -> list[QuoteLineIn]:
        return [QuoteLineIn(ln.id, prices[ln.item.name]) for ln in pr.lines]

    @staticmethod
    def _po_line_id(po: PurchaseOrder, item_name: str) -> int:
        return next(pl.id for pl in po.lines if pl.item.name == item_name)

    def grn_lines(self, po: PurchaseOrder, lines: dict[str, tuple]) -> list[GRNLineIn]:
        """item → (received, accepted, rejected, rejection_reason)"""
        return [GRNLineIn(self._po_line_id(po, name), r, a, x, why) for name, (r, a, x, why) in lines.items()]

    def invoice_lines(self, po: PurchaseOrder, lines: dict[str, tuple[str, str]]) -> list[InvoiceLineIn]:
        """item → (qty, unit_price)"""
        return [InvoiceLineIn(self._po_line_id(po, name), q, price) for name, (q, price) in lines.items()]

    def quote(self, pr, supplier: str, prices: dict[str, str], delivery_days: int, terms: str, days_ago: float):
        day = self.at(days_ago)
        return quotation_service.add_quotation(
            self.db, self.u("purchase"), pr, supplier_id=self.suppliers[supplier].id, quote_date=day,
            valid_until=day + timedelta(days=30), delivery_days=delivery_days, payment_terms=terms,
            lines=self.quote_lines(pr, prices),
        )


# --------------------------------------------------------------------------------------------
# Scenarios, oldest first so document numbers follow the timeline
# --------------------------------------------------------------------------------------------


def scenario_closed_po(d: Demo):
    """PR-0001 / PO-0001: low value (dept head only), fully received, invoiced, paid → CLOSED."""
    riya, db = d.u("requester.it"), d.db
    day = d.at(21.8)
    pr = pr_service.create_pr(db, riya, justification="Replacement keyboards and mice for the new support desk bay.",
                              required_by=day + timedelta(days=21),
                              lines=d.pr_lines((KEYBOARD, "10", "1500"), (MOUSE, "10", "800")))
    d.at(21.7); pr_service.submit_pr(db, riya, pr)
    d.at(20.9); pr_service.approve_pr(db, d.u("head.it"), pr, comment="OK, within team budget.")
    infoline = d.quote(pr, "Infoline Computers", {KEYBOARD: "1400", MOUSE: "750"}, 5, "30 days from invoice", 19.8)
    d.quote(pr, "Techno Solutions Pvt Ltd", {KEYBOARD: "1450", MOUSE: "800"}, 3, "30 days from invoice", 19.7)
    d.at(18.9); po = quotation_service.select_quotation(db, d.u("purchase"), pr, infoline)
    day = d.at(15.8)
    grn_service.record_grn(db, d.u("store"), po, received_date=day,
                           lines=d.grn_lines(po, {KEYBOARD: ("10", "10", "0", None), MOUSE: ("10", "10", "0", None)}))
    day = d.at(13.8)
    inv = invoice_service.enter_invoice(db, d.u("accounts"), po, supplier_invoice_number="INF/2026/0412",
                                        invoice_date=day, total="21500",
                                        lines=d.invoice_lines(po, {KEYBOARD: ("10", "1400"), MOUSE: ("10", "750")}))
    day = d.at(10.8)  # full payment → PO auto-closes
    payment_service.record_payment(db, d.u("accounts"), inv, amount="21500", mode=PaymentMode.NEFT,
                                   reference_no="HDFCN52026091100418", paid_on=day)


def scenario_short_closed_po(d: Demo):
    """PR-0002 / PO-0002: above threshold (dept head + finance), partly delivered, SHORT_CLOSED.
    The first invoice is billed at list price → MISMATCH → REJECTED; the corrected invoice reuses
    the number (D-03), is MATCHED and part-paid. Paying the ₹38,000 balance closes the PO."""
    riya, db, accounts = d.u("requester.it"), d.db, d.u("accounts")
    day = d.at(20.8)
    pr = pr_service.create_pr(db, riya, justification="Dual-monitor setup for the analytics team (20 seats).",
                              required_by=day + timedelta(days=25), lines=d.pr_lines((MONITOR, "20", "12000")))
    d.at(20.7); pr_service.submit_pr(db, riya, pr)
    d.at(19.9); pr_service.approve_pr(db, d.u("head.it"), pr)
    d.at(19.2); pr_service.approve_pr(db, d.u("finance"), pr, comment="Approved against Q3 IT capex.")
    techno = d.quote(pr, "Techno Solutions Pvt Ltd", {MONITOR: "11500"}, 7, "45 days from invoice", 17.9)
    d.quote(pr, "Digital Edge Systems", {MONITOR: "11800"}, 10, "30 days from invoice", 17.8)
    d.at(16.9); po = quotation_service.select_quotation(db, d.u("purchase"), pr, techno)
    day = d.at(12.8)
    grn_service.record_grn(db, d.u("store"), po, received_date=day, lines=d.grn_lines(po, {MONITOR: ("12", "12", "0", None)}),
                           remarks="Supplier short-shipped; balance promised next week.")
    day = d.at(9.8)
    wrong = invoice_service.enter_invoice(db, accounts, po, supplier_invoice_number="TSPL/2026/1187", invoice_date=day,
                                          total="144000", lines=d.invoice_lines(po, {MONITOR: ("12", "12000")}))
    d.at(8.8)
    po_service.short_close_po(db, d.u("purchase"), po,
                              reason="Supplier has discontinued this model; the remaining 8 units will be raised on a new PR.")
    d.at(7.9)
    invoice_service.reject_invoice(db, accounts, wrong,
                                   reason="Billed at list price instead of the PO price. Supplier to reissue at ₹11,500.")
    day = d.at(5.8)
    corrected = invoice_service.enter_invoice(db, accounts, po, supplier_invoice_number="TSPL/2026/1187",
                                              invoice_date=day, total="138000",
                                              lines=d.invoice_lines(po, {MONITOR: ("12", "11500")}))
    day = d.at(2.9)
    payment_service.record_payment(db, accounts, corrected, amount="100000", mode=PaymentMode.NEFT,
                                   reference_no="ICICN52026092000731", paid_on=day)


def scenario_partial_po_with_mismatch(d: Demo):
    """PR-0003 / PO-0003: single quote with justification; partial GRN with rejected steel; the
    supplier invoiced the rejected kilos too → MISMATCH (for the rematch/reject demo)."""
    karan, db = d.u("requester.ops"), d.db
    day = d.at(16.8)
    pr = pr_service.create_pr(db, karan, justification="Steel for mezzanine racking in Warehouse B, plus helmets "
                                                       "for the install crew.",
                              required_by=day + timedelta(days=20),
                              lines=d.pr_lines((STEEL, "500", "90"), (HELMET, "20", "600")))
    d.at(16.7); pr_service.submit_pr(db, karan, pr)
    d.at(15.9); pr_service.approve_pr(db, d.u("head.ops"), pr)
    d.at(14.9); pr_service.approve_pr(db, d.u("finance"), pr)
    shree = d.quote(pr, "Shree Steel & Safety Traders", {STEEL: "88", HELMET: "550"}, 4, "15 days from invoice", 13.9)
    d.at(12.9)
    po = quotation_service.select_quotation(
        db, d.u("purchase"), pr, shree,
        single_quote_justification="Only BIS-certified IS 2062 steel stockist that delivers to our Pune site within "
                                   "a week; two other vendors declined to quote.")
    day = d.at(9.8)
    grn_service.record_grn(db, d.u("store"), po, received_date=day,
                           lines=d.grn_lines(po, {STEEL: ("300", "280", "20", "Surface rust on 20 kg"),
                                                  HELMET: ("20", "20", "0", None)}),
                           remarks="First lot of steel; balance 200 kg due next week.")
    day = d.at(6.9)
    invoice_service.enter_invoice(db, d.u("accounts"), po, supplier_invoice_number="SSST/26-27/0923", invoice_date=day,
                                  total="37400", lines=d.invoice_lines(po, {STEEL: ("300", "88"), HELMET: ("20", "550")}))


def scenario_rejected_pr(d: Demo):
    """PR-0004: rejected by the dept head, ready to edit and resubmit."""
    karan, db = d.u("requester.ops"), d.db
    day = d.at(11.8)
    pr = pr_service.create_pr(db, karan, justification="Quarterly stationery for the dispatch office.",
                              required_by=day + timedelta(days=14),
                              lines=d.pr_lines((PAPER, "40", "260"), (PENS, "10", "350")))
    d.at(11.7); pr_service.submit_pr(db, karan, pr)
    d.at(10.9)
    pr_service.reject_pr(db, d.u("head.ops"), pr,
                         comment="Store still has 25 boxes of A4 paper. Reduce the paper quantity and resubmit.")


def scenario_approved_pr_with_three_quotes(d: Demo):
    """PR-0005: APPROVED with 3 quotes. Infoline is cheapest overall but slowest; the laptop is
    cheapest at Infoline, the dock at Techno — picking anyone but Infoline needs a reason."""
    riya, db = d.u("requester.it"), d.db
    day = d.at(8.8)
    pr = pr_service.create_pr(db, riya, justification="Laptops and docks for five new data-engineering hires "
                                                      "joining next month.",
                              required_by=day + timedelta(days=30),
                              lines=d.pr_lines((LAPTOP, "5", "72000"), (DOCK, "5", "9000")))
    d.at(8.7); pr_service.submit_pr(db, riya, pr)
    d.at(7.9); pr_service.approve_pr(db, d.u("head.it"), pr, comment="Headcount approved in the Q3 plan.")
    d.at(6.9); pr_service.approve_pr(db, d.u("finance"), pr)
    d.quote(pr, "Techno Solutions Pvt Ltd", {LAPTOP: "69500", DOCK: "8200"}, 7, "30 days from invoice", 4.9)
    d.quote(pr, "Digital Edge Systems", {LAPTOP: "68900", DOCK: "9100"}, 5, "45 days from invoice", 4.8)
    d.quote(pr, "Infoline Computers", {LAPTOP: "67800", DOCK: "9400"}, 21, "50% advance, 50% on delivery", 3.9)


def scenario_dept_head_pr(d: Demo):
    """PR-0006: raised by the IT dept head, below threshold, yet waiting on FINANCE (D-01)."""
    head, db = d.u("head.it"), d.db
    day = d.at(5.8)
    pr = pr_service.create_pr(db, head, justification="Speakerphones for the two new meeting rooms on the 4th floor.",
                              required_by=day + timedelta(days=15), lines=d.pr_lines((SPEAKERPHONE, "2", "18500")))
    d.at(5.7); pr_service.submit_pr(db, head, pr)


def scenario_pending_over_budget(d: Demo):
    """PR-0007: waiting on the Operations dept head. Operations has ₹55,000 committed this month
    (PO-0003); ₹4,49,000 more exceeds the ₹5,00,000 budget → over-budget warning."""
    karan, db = d.u("requester.ops"), d.db
    day = d.at(2.8)
    pr = pr_service.create_pr(db, karan, justification="Material handling for the Bay 3 go-live.",
                              required_by=day + timedelta(days=21),
                              lines=d.pr_lines((PALLET_TRUCK, "10", "42000"), (TAPE, "20", "1450")))
    d.at(2.7); pr_service.submit_pr(db, karan, pr)


def scenario_draft(d: Demo):
    """PR-0008: an unsubmitted draft (visible only to Riya, D-45)."""
    day = d.at(0.9)
    pr_service.create_pr(d.db, d.u("requester.it"), justification="Printer paper for the IT floor.",
                         required_by=day + timedelta(days=10), lines=d.pr_lines((PAPER, "10", "260")))


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


def reset_schema(bind: Engine = engine) -> None:
    """Drop every table (including ones no longer in the models) and recreate the schema."""
    existing = MetaData()
    existing.reflect(bind)
    existing.drop_all(bind)
    Base.metadata.create_all(bind)


def seed_masters(d: Demo, password_hash: str | None = None) -> None:
    """Users are the bootstrap: inserted directly with one shared demo hash. Everything else is
    created by ADMIN through master_service, so it passes the same validation as the UI."""
    db = d.db
    password_hash = password_hash or hash_password(settings.demo_password)
    pending_users = [
        User(name=name, email=email, password_hash=password_hash, role=role, is_active=True)
        for name, email, role, _ in USERS
    ]
    admin = next(u for u in pending_users if u.role is Role.ADMIN)
    db.add(admin)
    db.flush()

    for key, value in SETTING_DEFAULTS.items():
        master_service.set_setting(db, admin, key.value, value)
    departments = {
        name: master_service.create_department(db, admin, name=name, monthly_budget=budget)
        for name, budget in DEPARTMENTS
    }
    for user, (_, email, _, dept) in zip(pending_users, USERS, strict=True):
        user.department = departments[dept] if dept else None
        db.add(user)
        d.users[email.split("@")[0]] = user
    for name, contact, email, phone, gstin in SUPPLIERS:
        d.suppliers[name] = master_service.create_supplier(db, admin, name=name, contact_person=contact, email=email,
                                                           phone=phone, gstin=gstin)
    for name, unit, category in ITEMS:
        d.items[name] = master_service.create_item(db, admin, name=name, unit=unit, category=category)
    db.flush()


def seed(db: Session, *, password_hash: str | None = None, now: datetime | None = None) -> Demo:
    """Load masters and scenarios into an empty schema, then verify. Does not commit."""
    d = Demo(db, SeedClock(now))
    with clock.frozen_at(d.clock.at(SeedClock.SPAN)):  # restores the caller's clock afterwards
        seed_masters(d, password_hash)
        for scenario in SCENARIOS:
            scenario(d)
    db.flush()
    problems = verify(db)
    if problems:
        raise RuntimeError("Seed data is inconsistent:\n  - " + "\n  - ".join(problems))
    return d


def summary(db: Session) -> str:
    rows = [f"{pr.pr_number}  {pr.status:<17} {pr.department.name:<10} ₹{pr.estimated_total:>12,.2f}  "
            + ", ".join(f"{po.po_number} {po.status}" for po in pr.purchase_orders)
            for pr in db.scalars(select(PurchaseRequest).order_by(PurchaseRequest.id))]
    invoices = [f"{inv.supplier_invoice_number:<16} {inv.po.po_number}  {inv.status}"
                + (f"  — {inv.mismatch_details.splitlines()[0]}" if inv.status == "MISMATCH" else "")
                for inv in db.scalars(select(Invoice).order_by(Invoice.id))]
    return "\n".join(["Purchase requests:", *("  " + r for r in rows), "Invoices:", *("  " + i for i in invoices)])


def _has_data() -> bool:
    try:
        with SessionLocal() as db:
            return db.scalar(select(User.id).limit(1)) is not None
    except Exception:  # no tables yet
        return False


def main() -> None:
    if "--if-empty" in sys.argv[1:] and _has_data():
        print(f"Database already seeded ({engine.url}); leaving it as it is.")
        return
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
