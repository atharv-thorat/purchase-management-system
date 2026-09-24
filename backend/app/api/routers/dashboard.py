"""Role-aware dashboard summary and the audit log (timelines, recent activity)."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api import views
from app.api.common import ERROR_RESPONSES, READ_ROLES, Allow, DateFrom, DateTo, PagingParams, in_date_range
from app.core.deps import DbSession
from app.models import AuditLog
from app.models.enums import AuditAction, EntityType
from app.schemas.common import DepartmentRef, Page, TimelineEntry
from app.schemas.dashboard import DashboardOut, DepartmentSpendOut, PendingPaymentsOut
from app.services import access, dashboard_service

router = APIRouter(tags=["dashboard & audit"], responses=ERROR_RESPONSES)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: DbSession, user: Allow(*READ_ROLES)):
    """Everything the caller's dashboard shows, scoped to what they may see. Widgets that
    don't apply to the caller's role are null."""
    approvals = dashboard_service.pending_approvals(db, user)
    mismatches = dashboard_service.mismatch_invoices(db, user)
    payments = dashboard_service.pending_payments(db, user)
    spend = dashboard_service.spend_vs_budget(db, user)
    return DashboardOut(
        pending_approvals=[views.pending_approval(db, pr) for pr in approvals] if approvals is not None else None,
        my_requests=dashboard_service.my_requests(db, user),
        pos_by_status=dashboard_service.pos_by_status(db, user),
        mismatch_invoices=[views.invoice_list_item(i) for i in mismatches] if mismatches is not None else None,
        pending_payments=PendingPaymentsOut(count=payments.count, total_due=payments.total_due,
                                            invoices=[views.invoice_list_item(i) for i in payments.invoices])
        if payments else None,
        spend_vs_budget=[DepartmentSpendOut(department=DepartmentRef.model_validate(s.department),
                                            monthly_budget=s.department.monthly_budget, committed=s.committed,
                                            remaining=s.remaining, utilisation_pct=s.utilisation_pct,
                                            over_budget=s.over_budget) for s in spend] if spend is not None else None,
        recent_activity=views.timeline_entries(db, dashboard_service.recent_activity(db, user)),
    )


@router.get("/audit-logs", response_model=Page[TimelineEntry])
def audit_logs(
    db: DbSession,
    user: Allow(*READ_ROLES),
    paging: PagingParams,
    entity_type: EntityType | None = None,
    entity_id: int | None = None,
    action: AuditAction | None = None,
    at_from: DateFrom = None,
    at_to: DateTo = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$", description="asc for timelines, desc for activity")] = "desc",
):
    """Status history. Rows are visible exactly when the record they describe is (D-44, D-45)."""
    stmt = select(AuditLog).options(selectinload(AuditLog.user)).where(access.audit_visible_filter(user))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = in_date_range(stmt, AuditLog.at, at_from, at_to)
    stmt = stmt.order_by(AuditLog.at.asc(), AuditLog.id.asc()) if order == "asc" else \
        stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc())
    total_page = views.paginate(db, stmt, paging.page, paging.page_size, lambda r: r)
    return Page.of(views.timeline_entries(db, total_page.items), total_page.total, paging.page, paging.page_size)
