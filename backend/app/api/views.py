"""Presenters: ORM objects → response schemas, plus list pagination.

No business rules here. Everything a detail screen needs is gathered in one call, and parts
the caller may not read (GRNs for FINANCE, payments for PURCHASE, ...) come back as null.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AuditLog,
    GoodsReceipt,
    Invoice,
    Payment,
    PurchaseOrder,
    PurchaseRequest,
    Quotation,
    User,
)
from app.models.enums import EntityType, PRStatus, Role
from app.schemas.common import ItemRef, Page, SupplierRef, TimelineEntry, UserRef
from app.schemas.invoices import InvoiceDetail, InvoiceLineOut, InvoiceListItem
from app.schemas.pos import (
    GRNLineOut,
    GRNOut,
    InvoiceLink,
    PaymentOut,
    PODetail,
    POLineOut,
    POListItem,
    PORef,
    Receivable,
    ReceivableLine,
)
from app.schemas.prs import (
    ApprovalOut,
    BudgetOut,
    PendingApproval,
    POLink,
    PRDetail,
    PRLineOut,
    PRListItem,
)
from app.schemas.quotations import (
    ComparisonCell,
    ComparisonOut,
    ComparisonQuotation,
    ComparisonRow,
    QuotationOut,
    QuoteLineOut,
    SelectionHints,
)
from app.services import access, actions, grn_service, pr_service, quotation_service
from app.services._common import line_amount
from app.services.payment_service import amount_paid, balance_due
from app.services.pr_service import BudgetCheck

T = TypeVar("T")


# ---- pagination -----------------------------------------------------------------------------------


def paginate(db: Session, stmt: Select, page: int, page_size: int, present: Callable[[Any], T]) -> Page[T]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return Page.of([present(r) for r in rows], total, page, page_size)


# ---- audit timeline -------------------------------------------------------------------------------


def _references(db: Session, rows: Iterable[AuditLog]) -> dict[tuple[EntityType, int], str]:
    ids: dict[EntityType, set[int]] = defaultdict(set)
    for r in rows:
        ids[r.entity_type].add(r.entity_id)
    refs: dict[tuple[EntityType, int], str] = {}
    for entity_type, column in ((EntityType.PURCHASE_REQUEST, PurchaseRequest.pr_number),
                                (EntityType.PURCHASE_ORDER, PurchaseOrder.po_number),
                                (EntityType.INVOICE, Invoice.supplier_invoice_number)):
        if ids.get(entity_type):
            model = column.class_
            for entity_id, ref in db.execute(select(model.id, column).where(model.id.in_(ids[entity_type]))):
                refs[(entity_type, entity_id)] = ref
    return refs


def timeline_entries(db: Session, rows: list[AuditLog]) -> list[TimelineEntry]:
    refs = _references(db, rows)
    return [
        TimelineEntry(at=r.at, entity_type=r.entity_type, entity_id=r.entity_id,
                      reference=refs.get((r.entity_type, r.entity_id)), action=r.action,
                      from_status=r.from_status, to_status=r.to_status,
                      user=UserRef.model_validate(r.user) if r.user else None, details=r.details)
        for r in rows
    ]


def timeline(db: Session, *entities: tuple[EntityType, Iterable[int]]) -> list[TimelineEntry]:
    clauses = [(AuditLog.entity_type == et) & AuditLog.entity_id.in_(list(ids)) for et, ids in entities if ids]
    if not clauses:
        return []
    rows = db.scalars(select(AuditLog).options(selectinload(AuditLog.user)).where(or_(*clauses))
                      .order_by(AuditLog.at, AuditLog.id)).all()
    return timeline_entries(db, list(rows))


# ---- purchase requests ----------------------------------------------------------------------------


def budget_out(check: BudgetCheck) -> BudgetOut:
    return BudgetOut(department=check.department, monthly_budget=check.monthly_budget,
                     approved_this_month=check.approved_this_month, this_request=check.this_request,
                     projected=check.projected, remaining_after=check.remaining_after, over_budget=check.over_budget)


def pr_list_item(pr: PurchaseRequest) -> PRListItem:
    return PRListItem.model_validate(pr)


def pr_detail(db: Session, pr: PurchaseRequest, user: User) -> PRDetail:
    pending = pr.status in (PRStatus.PENDING_DEPT_HEAD, PRStatus.PENDING_FINANCE)
    show_budget = pending and user.role in (Role.DEPT_HEAD, Role.FINANCE, Role.ADMIN)
    return PRDetail(
        **pr_list_item(pr).model_dump(),
        rejection_reason=pr.rejection_reason,
        updated_at=pr.updated_at,
        lines=[PRLineOut(id=ln.id, item=ItemRef.model_validate(ln.item), quantity=ln.quantity,
                         estimated_unit_price=ln.estimated_unit_price,
                         line_total=line_amount(ln.quantity, ln.estimated_unit_price)) for ln in pr.lines],
        approvals=[ApprovalOut.model_validate(log) for log in pr.approval_logs],
        budget=budget_out(pr_service.budget_check(db, pr)) if show_budget else None,
        quotation_count=len(pr.quotations) if access.can_read(Quotation, user) else None,
        purchase_orders=[POLink.model_validate(po) for po in pr.purchase_orders]
        if access.can_read(PurchaseOrder, user) else None,
        timeline=timeline(db, (EntityType.PURCHASE_REQUEST, [pr.id])),
        actions=actions.pr_actions(pr, user),
    )


def pending_approval(db: Session, pr: PurchaseRequest) -> PendingApproval:
    level = "DEPT_HEAD" if pr.status is PRStatus.PENDING_DEPT_HEAD else "FINANCE"
    return PendingApproval(**pr_list_item(pr).model_dump(), level=level,
                           budget=budget_out(pr_service.budget_check(db, pr)))


# ---- quotations -----------------------------------------------------------------------------------


def quotation_out(q: Quotation) -> QuotationOut:
    return QuotationOut(
        id=q.id, pr_id=q.pr_id, supplier=SupplierRef.model_validate(q.supplier), quote_date=q.quote_date,
        valid_until=q.valid_until, delivery_days=q.delivery_days, payment_terms=q.payment_terms, total=q.total,
        is_selected=q.is_selected, is_expired=quotation_service.is_expired(q), created_at=q.created_at,
        lines=[QuoteLineOut(id=ql.id, pr_line_id=ql.pr_line_id, item=ItemRef.model_validate(ql.pr_line.item),
                            quantity=ql.pr_line.quantity, unit_price=ql.unit_price,
                            line_total=line_amount(ql.pr_line.quantity, ql.unit_price)) for ql in q.lines],
    )


def comparison_out(pr: PurchaseRequest) -> ComparisonOut:
    cmp = quotation_service.compare(pr)
    quotes = list(pr.quotations)
    lowest_total = min((cmp.totals[qid] for qid in cmp.lowest_valid_total), default=None)
    rows = []
    for pr_line, line in zip(pr.lines, cmp.lines, strict=True):
        cells = [ComparisonCell(quotation_id=q.id, unit_price=line.prices[q.id],
                                line_total=line_amount(line.quantity, line.prices[q.id]), is_lowest=q.id in line.lowest)
                 for q in quotes if q.id in line.prices]
        rows.append(ComparisonRow(pr_line_id=line.pr_line_id, item=ItemRef.model_validate(pr_line.item),
                                  quantity=line.quantity, cells=cells))
    return ComparisonOut(
        pr_id=pr.id, pr_number=pr.pr_number, pr_status=pr.status,
        quotations=[ComparisonQuotation(
            quotation_id=q.id, supplier=SupplierRef.model_validate(q.supplier), total=q.total,
            delivery_days=q.delivery_days, payment_terms=q.payment_terms, quote_date=q.quote_date,
            valid_until=q.valid_until, is_expired=q.id in cmp.expired, is_selected=q.is_selected,
            is_lowest_valid_total=q.id in cmp.lowest_valid_total) for q in quotes],
        lines=rows,
        selection=SelectionHints(valid_quotations=cmp.valid_count,
                                 single_quote_justification_required=cmp.valid_count < 2,
                                 lowest_valid_total=lowest_total,
                                 lowest_valid_quotation_ids=sorted(cmp.lowest_valid_total)),
    )


# ---- purchase orders, GRNs, payments --------------------------------------------------------------


def po_ref(po: PurchaseOrder) -> PORef:
    return PORef.model_validate(po)


def po_list_item(po: PurchaseOrder) -> POListItem:
    return POListItem.model_validate(po)


def grn_out(grn: GoodsReceipt) -> GRNOut:
    return GRNOut(
        id=grn.id, grn_number=grn.grn_number, po=po_ref(grn.po), received_date=grn.received_date,
        received_by=UserRef.model_validate(grn.receiver), remarks=grn.remarks, created_at=grn.created_at,
        lines=[GRNLineOut(id=gl.id, po_line_id=gl.po_line_id, item=ItemRef.model_validate(gl.po_line.item),
                          qty_received=gl.qty_received, qty_accepted=gl.qty_accepted, qty_rejected=gl.qty_rejected,
                          rejection_reason=gl.rejection_reason) for gl in grn.lines],
    )


def receivable_out(po: PurchaseOrder) -> Receivable:
    return Receivable(po=po_ref(po), lines=[
        ReceivableLine(po_line_id=r.po_line.id, item=ItemRef.model_validate(r.po_line.item),
                       qty_ordered=r.po_line.qty_ordered, qty_accepted=r.po_line.qty_accepted, qty_pending=r.pending)
        for r in grn_service.receivable(po)
    ])


def payment_out(p: Payment) -> PaymentOut:
    inv = p.invoice
    return PaymentOut(id=p.id, invoice_id=inv.id, supplier_invoice_number=inv.supplier_invoice_number,
                      po_number=inv.po.po_number, supplier=SupplierRef.model_validate(inv.supplier), amount=p.amount,
                      mode=p.mode, reference_no=p.reference_no, paid_on=p.paid_on,
                      recorded_by=UserRef.model_validate(p.recorder), created_at=p.created_at)


def invoice_link(inv: Invoice) -> InvoiceLink:
    return InvoiceLink(id=inv.id, supplier_invoice_number=inv.supplier_invoice_number, status=inv.status,
                       invoice_date=inv.invoice_date, total=inv.total, amount_paid=amount_paid(inv),
                       balance_due=balance_due(inv))


def po_detail(db: Session, po: PurchaseOrder, user: User) -> PODetail:
    sees_invoices = access.can_read(Invoice, user)
    return PODetail(
        **po_list_item(po).model_dump(),
        quotation_id=po.quotation_id, selection_reason=po.selection_reason,
        single_quote_justification=po.single_quote_justification, cancel_reason=po.cancel_reason,
        short_close_reason=po.short_close_reason, created_by=UserRef.model_validate(po.creator),
        lines=[POLineOut(id=pl.id, item=ItemRef.model_validate(pl.item), qty_ordered=pl.qty_ordered,
                         unit_price=pl.unit_price, line_total=line_amount(pl.qty_ordered, pl.unit_price),
                         qty_accepted=pl.qty_accepted, qty_invoiced=pl.qty_invoiced,
                         qty_pending_receipt=pl.qty_ordered - pl.qty_accepted,
                         qty_uninvoiced=pl.qty_accepted - pl.qty_invoiced) for pl in po.lines],
        goods_receipts=[grn_out(g) for g in po.goods_receipts] if access.can_read(GoodsReceipt, user) else None,
        invoices=[invoice_link(i) for i in po.invoices] if sees_invoices else None,
        payments=[payment_out(p) for i in po.invoices for p in i.payments]
        if access.can_read(Payment, user) else None,
        timeline=timeline(db, (EntityType.PURCHASE_ORDER, [po.id]),
                          (EntityType.INVOICE, [i.id for i in po.invoices] if sees_invoices else [])),
        actions=actions.po_actions(po, user),
    )


# ---- invoices -------------------------------------------------------------------------------------


def invoice_list_item(inv: Invoice) -> InvoiceListItem:
    return InvoiceListItem(id=inv.id, supplier_invoice_number=inv.supplier_invoice_number, status=inv.status,
                           po=po_ref(inv.po), supplier=SupplierRef.model_validate(inv.supplier),
                           invoice_date=inv.invoice_date, total=inv.total, amount_paid=amount_paid(inv),
                           balance_due=balance_due(inv), created_at=inv.created_at)


def invoice_detail(db: Session, inv: Invoice, user: User) -> InvoiceDetail:
    return InvoiceDetail(
        **invoice_list_item(inv).model_dump(),
        lines=[InvoiceLineOut(id=il.id, po_line_id=il.po_line_id, item=ItemRef.model_validate(il.po_line.item),
                              qty=il.qty, unit_price=il.unit_price, line_total=line_amount(il.qty, il.unit_price),
                              po_unit_price=il.po_line.unit_price,
                              price_matches=il.unit_price == il.po_line.unit_price) for il in inv.lines],
        mismatch_reasons=inv.mismatch_details.splitlines() if inv.mismatch_details else [],
        rejection_reason=inv.rejection_reason,
        created_by=UserRef.model_validate(inv.creator),
        payments=[payment_out(p) for p in inv.payments] if access.can_read(Payment, user) else None,
        timeline=timeline(db, (EntityType.INVOICE, [inv.id])),
        actions=actions.invoice_actions(inv, user),
    )
