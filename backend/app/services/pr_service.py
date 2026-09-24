"""Purchase requests: create/edit/delete/submit, approval routing, rejection, budget check."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.db import atomic
from app.core.errors import BusinessRuleViolation, Forbidden
from app.models.enums import (
    ApprovalAction,
    ApprovalLevel,
    AuditAction,
    DocumentType,
    POStatus,
    PRStatus,
    Role,
)
from app.models.master import Department, Item, User
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_request import ApprovalLog, PRLine, PurchaseRequest
from app.services import state_machine as sm
from app.services._common import (
    Problems,
    ensure_role,
    fmt_date,
    inr,
    line_amount,
    money,
    optional_text,
    quantity,
    require_text,
)
from app.services.master_service import finance_threshold
from app.services.numbering import next_number

PR_RAISERS = (Role.REQUESTER, Role.DEPT_HEAD)  # D-19
APPROVERS = (Role.DEPT_HEAD, Role.FINANCE)


@dataclass(frozen=True)
class PRLineIn:
    item_id: int
    quantity: Decimal | int | str
    estimated_unit_price: Decimal | int | str


# ---- drafting -------------------------------------------------------------------------------


def _check_required_by(required_by: date) -> None:
    if required_by < clock.today():
        raise BusinessRuleViolation(f"Required-by date {fmt_date(required_by)} is in the past")


def _build_lines(db: Session, lines: list[PRLineIn]) -> list[PRLine]:
    problems = Problems()
    if not lines:
        raise BusinessRuleViolation("A purchase request needs at least one line")
    built: list[PRLine] = []
    seen: set[int] = set()
    for n, line in enumerate(lines, start=1):
        item = db.get(Item, line.item_id)
        if item is None:
            problems.add(f"Line {n}: item {line.item_id} does not exist")
            continue
        where = f"Line {n} ({item.name})"
        if item.id in seen:
            problems.add(f"{where}: item appears more than once; combine it into one line")
        seen.add(item.id)
        try:
            qty = quantity(line.quantity, f"{where}: quantity")
            price = money(line.estimated_unit_price, f"{where}: estimated unit price")
        except BusinessRuleViolation as exc:
            problems.add(exc.message)
            continue
        built.append(PRLine(item=item, quantity=qty, estimated_unit_price=price))
    problems.raise_if_any()
    return built


def _set_content(db: Session, pr: PurchaseRequest, justification: str, required_by: date, lines: list[PRLineIn]):
    justification = require_text(justification, "Justification")
    _check_required_by(required_by)
    built = _build_lines(db, lines)
    pr.justification = justification
    pr.required_by = required_by
    pr.lines.clear()
    db.flush()
    pr.lines.extend(built)
    pr.estimated_total = sum((line_amount(ln.quantity, ln.estimated_unit_price) for ln in built), Decimal("0.00"))


def _ensure_owner(actor: User, pr: PurchaseRequest, to: str) -> None:
    if actor.id != pr.requester_id:
        raise Forbidden(f"Only the requester of {pr.pr_number} can {to} it")


@atomic
def create_pr(db: Session, actor: User, *, justification: str, required_by: date,
              lines: list[PRLineIn]) -> PurchaseRequest:
    ensure_role(actor, *PR_RAISERS, to="raise purchase requests")
    pr = PurchaseRequest(requester=actor, department_id=actor.department_id, status=PRStatus.DRAFT)
    _set_content(db, pr, justification, required_by, lines)
    pr.pr_number = next_number(db, DocumentType.PR)  # assigned at creation (D-31)
    db.add(pr)
    sm.create(db, pr, AuditAction.CREATED, actor)
    return pr


@atomic
def update_pr(db: Session, actor: User, pr: PurchaseRequest, *, justification: str, required_by: date,
              lines: list[PRLineIn]) -> PurchaseRequest:
    """Replace the content of a DRAFT or REJECTED PR."""
    _ensure_owner(actor, pr, "edit")
    sm.check(pr, AuditAction.EDITED)
    _set_content(db, pr, justification, required_by, lines)
    sm.transition(db, pr, AuditAction.EDITED, pr.status, actor)
    return pr


@atomic
def delete_pr(db: Session, actor: User, pr: PurchaseRequest) -> None:
    """Only DRAFTs can be deleted; there is no CANCELLED state (D-13)."""
    _ensure_owner(actor, pr, "delete")
    sm.delete(db, pr, AuditAction.DELETED, actor)


@atomic
def submit_pr(db: Session, actor: User, pr: PurchaseRequest) -> PurchaseRequest:
    """DRAFT → submit, REJECTED → resubmit. Both restart the chain at the requester's entry
    level: PENDING_DEPT_HEAD, or PENDING_FINANCE for a dept head's own PR (D-01, D-02)."""
    _ensure_owner(actor, pr, "submit")
    ensure_role(actor, *PR_RAISERS, to="submit purchase requests")
    action = AuditAction.RESUBMITTED if pr.status is PRStatus.REJECTED else AuditAction.SUBMITTED
    sm.check(pr, action)
    _check_required_by(pr.required_by)
    target = PRStatus.PENDING_FINANCE if actor.role is Role.DEPT_HEAD else PRStatus.PENDING_DEPT_HEAD
    pr.submitted_at = clock.now()
    pr.rejection_reason = None
    pr.final_approved_at = None
    sm.transition(db, pr, action, target, actor, {"routed_to": target.value})
    return pr


# ---- budget ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetCheck:
    department: str
    monthly_budget: Decimal
    approved_this_month: Decimal  # excluding the PR being checked
    this_request: Decimal
    projected: Decimal
    over_budget: bool

    @property
    def remaining_after(self) -> Decimal:
        return self.monthly_budget - self.projected


def committed_this_month(db: Session, department_id: int, *, exclude_pr_id: int | None = None) -> Decimal:
    """D-05: the department's PRs in APPROVED or PO_CREATED whose final approval falls in the
    current calendar month, each valued at its non-cancelled PO total if any, else its estimate."""
    live_po = and_(PurchaseOrder.pr_id == PurchaseRequest.id, PurchaseOrder.status != POStatus.CANCELLED)
    stmt = (
        select(func.coalesce(func.sum(func.coalesce(PurchaseOrder.total, PurchaseRequest.estimated_total)), 0))
        .select_from(PurchaseRequest)
        .outerjoin(PurchaseOrder, live_po)
        .where(
            PurchaseRequest.department_id == department_id,
            PurchaseRequest.status.in_([PRStatus.APPROVED, PRStatus.PO_CREATED]),
            PurchaseRequest.final_approved_at >= clock.month_start(),
            PurchaseRequest.final_approved_at < clock.next_month_start(),
        )
    )
    if exclude_pr_id is not None:
        stmt = stmt.where(PurchaseRequest.id != exclude_pr_id)
    return Decimal(db.scalar(stmt))


def budget_check(db: Session, pr: PurchaseRequest) -> BudgetCheck:
    """Rule 4: warn (never block) when this PR would take the department over budget."""
    dept = db.get(Department, pr.department_id)
    approved = committed_this_month(db, pr.department_id, exclude_pr_id=pr.id)
    projected = approved + pr.estimated_total
    return BudgetCheck(
        department=dept.name,
        monthly_budget=dept.monthly_budget,
        approved_this_month=approved,
        this_request=pr.estimated_total,
        projected=projected,
        over_budget=projected > dept.monthly_budget,
    )


# ---- approval -------------------------------------------------------------------------------


def _authorize_approver(actor: User, pr: PurchaseRequest, verb: str) -> ApprovalLevel:
    """Who may act on a pending PR (rule 2). Returns the approval level being acted on."""
    if actor.id == pr.requester_id:
        raise Forbidden(f"You cannot {verb} your own purchase request")
    if pr.status is PRStatus.PENDING_DEPT_HEAD:
        if actor.role is not Role.DEPT_HEAD or actor.department_id != pr.department_id:
            raise Forbidden(f"{pr.pr_number} is waiting for the {pr.department.name} department head")
        return ApprovalLevel.DEPT_HEAD
    if actor.role is not Role.FINANCE:
        raise Forbidden(f"{pr.pr_number} is waiting for Finance")
    return ApprovalLevel.FINANCE


def _log(pr: PurchaseRequest, actor: User, level: ApprovalLevel, action: ApprovalAction, comment: str | None,
         budget: BudgetCheck) -> None:
    pr.approval_logs.append(
        ApprovalLog(level=level, approver=actor, action=action, comment=comment,
                    over_budget=budget.over_budget, at=clock.now())  # snapshot of what was shown (D-36)
    )


@atomic
def approve_pr(db: Session, actor: User, pr: PurchaseRequest, *, comment: str | None = None) -> PurchaseRequest:
    """Dept-head approval routes to FINANCE above the threshold, read now (rule 1, D-12);
    FINANCE approval is final. An over-budget PR can still be approved; the warning is logged."""
    ensure_role(actor, *APPROVERS, to="approve purchase requests")
    sm.check(pr, AuditAction.APPROVED)
    level = _authorize_approver(actor, pr, "approve")
    budget = budget_check(db, pr)
    if level is ApprovalLevel.DEPT_HEAD and pr.estimated_total > finance_threshold(db):
        target = PRStatus.PENDING_FINANCE
    else:
        target = PRStatus.APPROVED
        pr.final_approved_at = clock.now()  # drives the budget month (D-05)
    _log(pr, actor, level, ApprovalAction.APPROVED, optional_text(comment), budget)
    details = {"level": level.value, "over_budget": budget.over_budget}
    if budget.over_budget:
        details["budget_note"] = (f"{inr(budget.projected)} projected against {inr(budget.monthly_budget)} "
                                  f"{budget.department} budget")
    sm.transition(db, pr, AuditAction.APPROVED, target, actor, details)
    return pr


@atomic
def reject_pr(db: Session, actor: User, pr: PurchaseRequest, *, comment: str) -> PurchaseRequest:
    """Rule 3: rejection needs a comment; the requester can then edit and resubmit."""
    ensure_role(actor, *APPROVERS, to="reject purchase requests")
    sm.check(pr, AuditAction.REJECTED)
    level = _authorize_approver(actor, pr, "reject")
    comment = require_text(comment, "A comment explaining the rejection")
    budget = budget_check(db, pr)
    _log(pr, actor, level, ApprovalAction.REJECTED, comment, budget)
    pr.rejection_reason = comment
    sm.transition(db, pr, AuditAction.REJECTED, PRStatus.REJECTED, actor, {"level": level.value, "comment": comment})
    return pr


def pending_approvals(db: Session, actor: User) -> list[PurchaseRequest]:
    """The approver's inbox: their department's PENDING_DEPT_HEAD PRs, or all PENDING_FINANCE
    PRs for FINANCE. Own PRs are never included."""
    stmt = select(PurchaseRequest).where(PurchaseRequest.requester_id != actor.id).order_by(PurchaseRequest.id)
    if actor.role is Role.DEPT_HEAD:
        stmt = stmt.where(PurchaseRequest.status == PRStatus.PENDING_DEPT_HEAD,
                          PurchaseRequest.department_id == actor.department_id)
    elif actor.role is Role.FINANCE:
        stmt = stmt.where(PurchaseRequest.status == PRStatus.PENDING_FINANCE)
    else:
        return []
    return list(db.scalars(stmt))
