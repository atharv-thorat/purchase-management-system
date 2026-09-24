"""Test fixtures: a fresh SQLite file per test, a frozen clock, the seed's master data, and a
`World` helper that drives records into any state through the real services."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.db import Base, make_engine
from app.core.security import hash_password
from app.models import AuditLog, Invoice, PurchaseOrder, PurchaseRequest, Quotation, User
from app.models.enums import PRStatus
from app.seed.seed import (
    DOCK,
    HELMET,
    KEYBOARD,
    LAPTOP,
    MONITOR,
    MOUSE,
    STEEL,
    Demo,
    SeedClock,
    seed_masters,
)
from app.services import (
    grn_service,
    invoice_service,
    payment_service,
    pr_service,
    quotation_service,
    state_machine,
)
from app.services.grn_service import GRNLineIn
from app.services.invoice_service import InvoiceLineIn
from app.services.pr_service import PRLineIn
from app.services.quotation_service import QuoteLineIn

__all__ = ["DOCK", "HELMET", "KEYBOARD", "LAPTOP", "MONITOR", "MOUSE", "STEEL"]

# Mid-month, so "this month" has room on both sides.
NOW = datetime(2026, 9, 15, 10, 0)

TECHNO = "Techno Solutions Pvt Ltd"
DIGITAL = "Digital Edge Systems"
INFOLINE = "Infoline Computers"
SHREE = "Shree Steel & Safety Traders"
BHARAT = "Bharat Office Supplies"

# 10 laptops at ₹1,000 = ₹10,000: below the ₹50,000 finance threshold.
SMALL = ((LAPTOP, "10", "1000"),)
# ₹60,000: above the threshold, so it needs FINANCE too.
LARGE = ((LAPTOP, "10", "6000"),)
TWO_LINES = ((LAPTOP, "10", "1000"), (MOUSE, "20", "100"))

D = Decimal


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password("demo123")  # bcrypt is slow; hash once


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.freeze(NOW)
    yield
    clock.freeze(None)


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


class World:
    """Seed masters plus shortcuts. Every shortcut goes through the services."""

    def __init__(self, db: Session, demo: Demo):
        self.db = db
        self.users = demo.users
        self.items = demo.items
        self.suppliers = demo.suppliers

    # ---- actors ---------------------------------------------------------------------------
    @property
    def requester(self) -> User:
        return self.users["requester.it"]

    @property
    def head(self) -> User:
        return self.users["head.it"]

    @property
    def requester_ops(self) -> User:
        return self.users["requester.ops"]

    @property
    def head_ops(self) -> User:
        return self.users["head.ops"]

    @property
    def finance(self) -> User:
        return self.users["finance"]

    @property
    def purchase(self) -> User:
        return self.users["purchase"]

    @property
    def store(self) -> User:
        return self.users["store"]

    @property
    def accounts(self) -> User:
        return self.users["accounts"]

    @property
    def admin(self) -> User:
        return self.users["admin"]

    def head_of(self, pr: PurchaseRequest) -> User:
        return self.head if pr.department.name == "IT" else self.head_ops

    # ---- time -----------------------------------------------------------------------------
    @staticmethod
    def later(**delta) -> None:
        clock.freeze(clock.now() + timedelta(**delta))

    # ---- purchase requests ----------------------------------------------------------------
    def pr_lines(self, lines) -> list[PRLineIn]:
        return [PRLineIn(self.items[name].id, q, price) for name, q, price in lines]

    def draft(self, requester: User | None = None, lines=SMALL, required_in: int = 30) -> PurchaseRequest:
        return pr_service.create_pr(self.db, requester or self.requester, justification="Needed for testing",
                                    required_by=clock.today() + timedelta(days=required_in),
                                    lines=self.pr_lines(lines))

    def submitted(self, requester: User | None = None, lines=SMALL) -> PurchaseRequest:
        pr = self.draft(requester, lines)
        return pr_service.submit_pr(self.db, pr.requester, pr)

    def approved(self, requester: User | None = None, lines=SMALL) -> PurchaseRequest:
        pr = self.submitted(requester, lines)
        if pr.status is PRStatus.PENDING_DEPT_HEAD:
            pr_service.approve_pr(self.db, self.head_of(pr), pr)
        if pr.status is PRStatus.PENDING_FINANCE:
            pr_service.approve_pr(self.db, self.finance, pr)
        assert pr.status is PRStatus.APPROVED
        return pr

    # ---- quotations and POs ---------------------------------------------------------------
    def quote(self, pr: PurchaseRequest, supplier: str = TECHNO, prices: dict[str, str] | None = None,
              valid_days: int = 30, delivery_days: int = 7) -> Quotation:
        prices = prices or {}
        lines = [QuoteLineIn(ln.id, prices.get(ln.item.name, ln.estimated_unit_price)) for ln in pr.lines]
        return quotation_service.add_quotation(
            self.db, self.purchase, pr, supplier_id=self.suppliers[supplier].id, quote_date=clock.today(),
            valid_until=clock.today() + timedelta(days=valid_days), delivery_days=delivery_days,
            payment_terms="30 days", lines=lines)

    def po(self, lines=SMALL, requester: User | None = None, supplier: str = TECHNO,
           prices: dict[str, str] | None = None) -> PurchaseOrder:
        pr = self.approved(requester, lines)
        q = self.quote(pr, supplier, prices)
        return quotation_service.select_quotation(self.db, self.purchase, pr, q,
                                                  single_quote_justification="Sole approved vendor")

    # ---- receipts, invoices, payments -----------------------------------------------------
    @staticmethod
    def line(po: PurchaseOrder, item: str):
        return next(pl for pl in po.lines if pl.item.name == item)

    def receive(self, po: PurchaseOrder, accept: dict[str, str] | None = None,
                reject: dict[str, tuple[str, str]] | None = None):
        """accept: item → qty accepted (default: everything still pending);
        reject: item → (qty rejected, reason)."""
        if accept is None and reject is None:
            accept = {pl.item.name: pl.qty_ordered - pl.qty_accepted for pl in po.lines}
        accept, reject = accept or {}, reject or {}
        lines = []
        for name in dict.fromkeys([*accept, *reject]):
            a = D(accept.get(name, 0))
            r, why = reject.get(name, (0, None))
            lines.append(GRNLineIn(self.line(po, name).id, a + D(r), a, r, why))
        return grn_service.record_grn(self.db, self.store, po, received_date=clock.today(), lines=lines)

    def invoice(self, po: PurchaseOrder, number: str = "INV-001", lines: dict[str, tuple] | None = None,
                total=None) -> Invoice:
        """lines: item → (qty, unit_price). Default: all accepted-but-uninvoiced qty at PO price."""
        if lines is None:
            lines = {pl.item.name: (pl.qty_accepted - pl.qty_invoiced, pl.unit_price)
                     for pl in po.lines if pl.qty_accepted > pl.qty_invoiced}
        built = [InvoiceLineIn(self.line(po, name).id, q, p) for name, (q, p) in lines.items()]
        if total is None:
            total = sum((D(q) * D(p) for q, p in lines.values()), D("0"))
        return invoice_service.enter_invoice(self.db, self.accounts, po, supplier_invoice_number=number,
                                             invoice_date=clock.today(), total=total, lines=built)

    def pay(self, invoice: Invoice, amount=None):
        amount = payment_service.balance_due(invoice) if amount is None else amount
        return payment_service.record_payment(self.db, self.accounts, invoice, amount=amount, mode="NEFT",
                                              reference_no="UTR123", paid_on=clock.today())

    # ---- audit ----------------------------------------------------------------------------
    def audit(self, entity) -> list[tuple[str, str | None, str | None]]:
        entity_type, _ = state_machine.TABLES[type(entity)]
        rows = self.db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity.id)
            .order_by(AuditLog.id)
        )
        return [(r.action.value, r.from_status, r.to_status) for r in rows]


@pytest.fixture
def w(db, password_hash) -> World:
    demo = Demo(db, SeedClock(NOW))
    seed_masters(demo, password_hash)
    return World(db, demo)


# ---- API tests ------------------------------------------------------------------------------------


class RoleClient:
    """A TestClient that sends one user's bearer token on every request."""

    def __init__(self, client, token: str):
        self.client, self.headers = client, {"Authorization": f"Bearer {token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json, headers=self.headers, **kw)

    def put(self, url, json=None, **kw):
        return self.client.put(url, json=json, headers=self.headers, **kw)

    def patch(self, url, json=None, **kw):
        return self.client.patch(url, json=json, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers, **kw)


class Api:
    """The demo seed behind a TestClient. `api.as_("finance")` → client for that user;
    `api.id(PurchaseOrder, "PO-0003")` → database id of a numbered document."""

    def __init__(self, client, users: dict[str, int], session_factory):
        self.client, self.users, self._sessions = client, users, session_factory

    def as_(self, user_key: str) -> RoleClient:
        from app.core.security import create_access_token

        user_id, role = self.users[user_key]
        return RoleClient(self.client, create_access_token(user_id, role)[0])

    def id(self, model, number: str) -> int:
        column = {PurchaseRequest: PurchaseRequest.pr_number, PurchaseOrder: PurchaseOrder.po_number,
                  Invoice: Invoice.supplier_invoice_number}[model]
        with self._sessions() as s:
            return s.scalars(select(model.id).where(column == number).order_by(model.id.desc())).first()


@pytest.fixture
def api(engine, password_hash):
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import app
    from app.seed.seed import seed

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as s:
        demo = seed(s, password_hash=password_hash, now=NOW)
        s.commit()
        users = {key: (u.id, u.role) for key, u in demo.users.items()}

    def session_per_request():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = session_per_request
    with TestClient(app) as client:
        yield Api(client, users, sessions)
    app.dependency_overrides.clear()
