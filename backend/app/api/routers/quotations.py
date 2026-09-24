"""Quotations per PR, the comparison view, and select-and-create-PO."""

from fastapi import APIRouter, Response, status

from app.api import views
from app.api.common import ERROR_RESPONSES, Allow
from app.core.deps import DbSession
from app.models import PurchaseRequest, Quotation
from app.models.enums import Role
from app.schemas.pos import PODetail
from app.schemas.quotations import ComparisonOut, QuotationIn, QuotationOut, QuotationUpdate, SelectIn
from app.services import access, quotation_service
from app.services.quotation_service import QuoteLineIn

router = APIRouter(tags=["quotations"], responses=ERROR_RESPONSES)
READERS = access.readers(Quotation)
P = Role.PURCHASE


def _lines(body: QuotationUpdate) -> list[QuoteLineIn]:
    return [QuoteLineIn(ln.pr_line_id, ln.unit_price) for ln in body.lines]


def _pr(db, pr_id: int, user) -> PurchaseRequest:
    return access.get_visible_or_404(db, PurchaseRequest, pr_id, user)


def _quotation(db, quotation_id: int, user) -> Quotation:
    return access.get_visible_or_404(db, Quotation, quotation_id, user)


@router.get("/prs/{pr_id}/quotations", response_model=list[QuotationOut])
def list_quotations(pr_id: int, db: DbSession, user: Allow(*READERS)):
    return [views.quotation_out(q) for q in _pr(db, pr_id, user).quotations]


@router.post("/prs/{pr_id}/quotations", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
def add_quotation(pr_id: int, body: QuotationIn, db: DbSession, user: Allow(P)):
    q = quotation_service.add_quotation(
        db, user, _pr(db, pr_id, user), supplier_id=body.supplier_id, quote_date=body.quote_date,
        valid_until=body.valid_until, delivery_days=body.delivery_days, payment_terms=body.payment_terms,
        lines=_lines(body))
    db.commit()
    return views.quotation_out(q)


@router.get("/prs/{pr_id}/quotations/comparison", response_model=ComparisonOut)
def compare_quotations(pr_id: int, db: DbSession, user: Allow(*READERS)):
    """Line-by-line prices per supplier. "Lowest" (per line and in total) counts only
    quotations that haven't expired; expired ones are shown and flagged (D-50)."""
    return views.comparison_out(_pr(db, pr_id, user))


@router.post("/prs/{pr_id}/quotations/{quotation_id}/select", response_model=PODetail,
             status_code=status.HTTP_201_CREATED)
def select_quotation(pr_id: int, quotation_id: int, db: DbSession, user: Allow(P), body: SelectIn | None = None):
    """Select a quotation and issue the PO in one step (D-33). Needs a single-quote
    justification with fewer than 2 valid quotations, and a selection reason when the choice
    isn't the lowest valid total (rule 6)."""
    body = body or SelectIn()
    po = quotation_service.select_quotation(
        db, user, _pr(db, pr_id, user), _quotation(db, quotation_id, user),
        selection_reason=body.selection_reason, single_quote_justification=body.single_quote_justification)
    db.commit()
    return views.po_detail(db, po, user)


@router.put("/quotations/{quotation_id}", response_model=QuotationOut)
def update_quotation(quotation_id: int, body: QuotationUpdate, db: DbSession, user: Allow(P)):
    q = _quotation(db, quotation_id, user)
    quotation_service.update_quotation(db, user, q, quote_date=body.quote_date, valid_until=body.valid_until,
                                       delivery_days=body.delivery_days, payment_terms=body.payment_terms,
                                       lines=_lines(body))
    db.commit()
    return views.quotation_out(q)


@router.delete("/quotations/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(quotation_id: int, db: DbSession, user: Allow(P)):
    quotation_service.delete_quotation(db, user, _quotation(db, quotation_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
