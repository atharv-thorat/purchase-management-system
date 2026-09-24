"""Purchase orders: list, detail, cancel, short-close."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api import views
from app.api.common import ERROR_RESPONSES, Allow, DateFrom, DateTo, PagingParams, in_date_range
from app.core.deps import DbSession
from app.models import PurchaseOrder, PurchaseRequest
from app.models.enums import POStatus, Role
from app.schemas.common import Page, ReasonIn
from app.schemas.pos import PODetail, POListItem
from app.services import access, po_service

router = APIRouter(tags=["purchase orders"], responses=ERROR_RESPONSES)
READERS = access.readers(PurchaseOrder)


def _load(db, po_id: int, user) -> PurchaseOrder:
    return access.get_visible_or_404(db, PurchaseOrder, po_id, user)


@router.get("/pos", response_model=Page[POListItem])
def list_pos(
    db: DbSession,
    user: Allow(*READERS),
    paging: PagingParams,
    status_: Annotated[list[POStatus] | None, Query(alias="status")] = None,
    supplier_id: int | None = None,
    department_id: int | None = None,
    pr_id: int | None = None,
    created_from: DateFrom = None,
    created_to: DateTo = None,
    q: Annotated[str | None, Query(description="PO number contains")] = None,
):
    stmt = access.scoped_select(PurchaseOrder, user).order_by(PurchaseOrder.id.desc())
    if status_:
        stmt = stmt.where(PurchaseOrder.status.in_(status_))
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if department_id:
        stmt = stmt.where(PurchaseOrder.pr_id.in_(
            select(PurchaseRequest.id).where(PurchaseRequest.department_id == department_id)))
    if pr_id:
        stmt = stmt.where(PurchaseOrder.pr_id == pr_id)
    if q:
        stmt = stmt.where(func.lower(PurchaseOrder.po_number).contains(q.lower()))
    stmt = in_date_range(stmt, PurchaseOrder.created_at, created_from, created_to)
    return views.paginate(db, stmt, paging.page, paging.page_size, views.po_list_item)


@router.get("/pos/{po_id}", response_model=PODetail)
def get_po(po_id: int, db: DbSession, user: Allow(*READERS)):
    """Lines with ordered / accepted / invoiced quantities, linked GRNs, invoices, payments and
    the audit timeline — whichever of those the caller may see."""
    return views.po_detail(db, _load(db, po_id, user), user)


@router.post("/pos/{po_id}/cancel", response_model=PODetail)
def cancel_po(po_id: int, body: ReasonIn, db: DbSession, user: Allow(Role.PURCHASE)):
    """Only an ISSUED PO with no goods receipt. The PR returns to APPROVED (D-06, D-17)."""
    po = _load(db, po_id, user)
    po_service.cancel_po(db, user, po, reason=body.reason)
    db.commit()
    return views.po_detail(db, po, user)


@router.post("/pos/{po_id}/short-close", response_model=PODetail)
def short_close_po(po_id: int, body: ReasonIn, db: DbSession, user: Allow(Role.PURCHASE)):
    """Stop further receipts on a PARTIALLY_RECEIVED PO (D-07). Closes at once if everything
    accepted is already invoiced and paid."""
    po = _load(db, po_id, user)
    po_service.short_close_po(db, user, po, reason=body.reason)
    db.commit()
    return views.po_detail(db, po, user)
