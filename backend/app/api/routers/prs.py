"""Purchase requests and the approval inbox. Handlers: check role, load in scope, call the
service, commit, present."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, or_

from app.api import views
from app.api.common import ERROR_RESPONSES, Allow, DateFrom, DateTo, PagingParams, in_date_range
from app.core.deps import DbSession
from app.models import PurchaseRequest
from app.models.enums import PRStatus, Role
from app.schemas.common import CommentIn, Page, RequiredCommentIn
from app.schemas.prs import BudgetOut, PendingApproval, PRDetail, PRIn, PRListItem
from app.services import access, pr_service
from app.services.pr_service import PRLineIn

router = APIRouter(tags=["purchase requests"], responses=ERROR_RESPONSES)
READERS = access.readers(PurchaseRequest)
RAISERS = (Role.REQUESTER, Role.DEPT_HEAD)
APPROVERS = (Role.DEPT_HEAD, Role.FINANCE)


def _lines(body: PRIn) -> list[PRLineIn]:
    return [PRLineIn(ln.item_id, ln.quantity, ln.estimated_unit_price) for ln in body.lines]


def _load(db, pr_id: int, user) -> PurchaseRequest:
    return access.get_visible_or_404(db, PurchaseRequest, pr_id, user)


@router.get("/prs", response_model=Page[PRListItem])
def list_prs(
    db: DbSession,
    user: Allow(*READERS),
    paging: PagingParams,
    status_: Annotated[list[PRStatus] | None, Query(alias="status")] = None,
    department_id: int | None = None,
    requester_id: int | None = None,
    mine: Annotated[bool, Query(description="Only PRs I raised")] = False,
    created_from: DateFrom = None,
    created_to: DateTo = None,
    q: Annotated[str | None, Query(description="PR number or justification contains")] = None,
):
    stmt = access.scoped_select(PurchaseRequest, user).order_by(PurchaseRequest.id.desc())
    if status_:
        stmt = stmt.where(PurchaseRequest.status.in_(status_))
    if department_id:
        stmt = stmt.where(PurchaseRequest.department_id == department_id)
    if requester_id:
        stmt = stmt.where(PurchaseRequest.requester_id == requester_id)
    if mine:
        stmt = stmt.where(PurchaseRequest.requester_id == user.id)
    if q:
        needle = q.lower()
        stmt = stmt.where(or_(func.lower(PurchaseRequest.pr_number).contains(needle),
                              func.lower(PurchaseRequest.justification).contains(needle)))
    stmt = in_date_range(stmt, PurchaseRequest.created_at, created_from, created_to)
    return views.paginate(db, stmt, paging.page, paging.page_size, views.pr_list_item)


@router.post("/prs", response_model=PRDetail, status_code=status.HTTP_201_CREATED)
def create_pr(body: PRIn, db: DbSession, user: Allow(*RAISERS)):
    pr = pr_service.create_pr(db, user, justification=body.justification, required_by=body.required_by,
                              lines=_lines(body))
    db.commit()
    return views.pr_detail(db, pr, user)


@router.get("/prs/{pr_id}", response_model=PRDetail)
def get_pr(pr_id: int, db: DbSession, user: Allow(*READERS)):
    return views.pr_detail(db, _load(db, pr_id, user), user)


@router.put("/prs/{pr_id}", response_model=PRDetail)
def update_pr(pr_id: int, body: PRIn, db: DbSession, user: Allow(*RAISERS)):
    pr = _load(db, pr_id, user)
    pr_service.update_pr(db, user, pr, justification=body.justification, required_by=body.required_by,
                         lines=_lines(body))
    db.commit()
    return views.pr_detail(db, pr, user)


@router.delete("/prs/{pr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pr(pr_id: int, db: DbSession, user: Allow(*RAISERS)):
    pr_service.delete_pr(db, user, _load(db, pr_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/prs/{pr_id}/submit", response_model=PRDetail)
def submit_pr(pr_id: int, db: DbSession, user: Allow(*RAISERS)):
    """Submit a DRAFT or resubmit a REJECTED PR. Routes to the dept head, or straight to
    FINANCE when a dept head raised it (D-01)."""
    pr = _load(db, pr_id, user)
    pr_service.submit_pr(db, user, pr)
    db.commit()
    return views.pr_detail(db, pr, user)


@router.post("/prs/{pr_id}/approve", response_model=PRDetail)
def approve_pr(pr_id: int, db: DbSession, user: Allow(*APPROVERS), body: CommentIn | None = None):
    pr = _load(db, pr_id, user)
    pr_service.approve_pr(db, user, pr, comment=body.comment if body else None)
    db.commit()
    return views.pr_detail(db, pr, user)


@router.post("/prs/{pr_id}/reject", response_model=PRDetail)
def reject_pr(pr_id: int, body: RequiredCommentIn, db: DbSession, user: Allow(*APPROVERS)):
    pr = _load(db, pr_id, user)
    pr_service.reject_pr(db, user, pr, comment=body.comment)
    db.commit()
    return views.pr_detail(db, pr, user)


@router.get("/prs/{pr_id}/budget-check", response_model=BudgetOut)
def budget_check(pr_id: int, db: DbSession, user: Allow(Role.DEPT_HEAD, Role.FINANCE, Role.ADMIN)):
    """Month-to-date committed spend for the PR's department, and whether this PR would exceed
    the budget (rule 4 / D-05). A warning only; approval is still allowed."""
    return views.budget_out(pr_service.budget_check(db, _load(db, pr_id, user)))


@router.get("/approvals/pending", response_model=list[PendingApproval])
def pending_approvals(db: DbSession, user: Allow(*APPROVERS)):
    """The caller's approval inbox, with the budget warning for each PR."""
    return [views.pending_approval(db, pr) for pr in pr_service.pending_approvals(db, user)]
