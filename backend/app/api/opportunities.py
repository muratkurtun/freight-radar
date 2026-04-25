"""Opportunities endpoint — the approved-signal list that sales users see.

Tenant-aware, any authenticated user can read. The `since` filter lets
the Angular UI fetch only items created after the last sync."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, tenant_context
from app.domain.enums import SignalType
from app.domain.schemas import Page, PagedOpportunities
from app.security.tenant_context import TenantContext
from app.services.opportunity_service import OpportunityService

router = APIRouter(
    prefix="/opportunities",
    tags=["opportunities"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("", response_model=PagedOpportunities)
def list_opportunities(
    signal_type: SignalType | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> PagedOpportunities:
    items, total = OpportunityService(db, ctx).list(
        signal_type=signal_type,
        since=since,
        limit=limit,
        offset=offset,
    )
    return PagedOpportunities(
        items=items,
        page=Page(limit=limit, offset=offset, total=total),
    )
