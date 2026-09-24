"""Goods receipts."""

from fastapi import APIRouter, status

from app.api import views
from app.api.common import ERROR_RESPONSES, Allow, DateFrom, DateTo, PagingParams, in_date_range
from app.core.deps import DbSession
from app.models import GoodsReceipt, PurchaseOrder
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.pos import GRNIn, GRNOut, Receivable
from app.services import access, grn_service
from app.services.grn_service import GRNLineIn

router = APIRouter(tags=["goods receipts"], responses=ERROR_RESPONSES)
READERS = access.readers(GoodsReceipt)


@router.get("/pos/{po_id}/receivable", response_model=Receivable)
def receivable(po_id: int, db: DbSession, user: Allow(Role.STORE)):
    """Quantity still to be accepted per line, to pre-fill the GRN form."""
    return views.receivable_out(access.get_visible_or_404(db, PurchaseOrder, po_id, user))


@router.post("/pos/{po_id}/grns", response_model=GRNOut, status_code=status.HTTP_201_CREATED)
def record_grn(po_id: int, body: GRNIn, db: DbSession, user: Allow(Role.STORE)):
    """Record a receipt. The PO's status is recomputed from accepted quantities (D-18); the
    response's `po.status` shows the result."""
    po = access.get_visible_or_404(db, PurchaseOrder, po_id, user)
    grn = grn_service.record_grn(
        db, user, po, received_date=body.received_date, remarks=body.remarks,
        lines=[GRNLineIn(ln.po_line_id, ln.qty_received, ln.qty_accepted, ln.qty_rejected, ln.rejection_reason)
               for ln in body.lines])
    db.commit()
    return views.grn_out(grn)


@router.get("/grns", response_model=Page[GRNOut])
def list_grns(db: DbSession, user: Allow(*READERS), paging: PagingParams, po_id: int | None = None,
              received_from: DateFrom = None, received_to: DateTo = None):
    stmt = access.scoped_select(GoodsReceipt, user).order_by(GoodsReceipt.id.desc())
    if po_id:
        stmt = stmt.where(GoodsReceipt.po_id == po_id)
    stmt = in_date_range(stmt, GoodsReceipt.received_date, received_from, received_to)
    return views.paginate(db, stmt, paging.page, paging.page_size, views.grn_out)


@router.get("/grns/{grn_id}", response_model=GRNOut)
def get_grn(grn_id: int, db: DbSession, user: Allow(*READERS)):
    return views.grn_out(access.get_visible_or_404(db, GoodsReceipt, grn_id, user))
