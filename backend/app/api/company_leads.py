"""Company-level lead view — sales-team primary screen.

Read-only. Tenant-scoped: any authenticated tenant user can read their
tenant's company leads (same auth shape as /opportunities). The
priority-derived team status, lead score, and feedback aggregates are
computed inside the SQL — see CompanyLeadRepository for the contract.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, tenant_context
from app.domain.schemas import (
    CompanyLeadDetail,
    CompanyLeadSummary,
    Page,
    PagedCompanyLeads,
)
from app.security.tenant_context import TenantContext
from app.services.company_lead_service import CompanyLeadService

router = APIRouter(
    prefix="/company-leads",
    tags=["company-leads"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("", response_model=PagedCompanyLeads)
def list_company_leads(
    sector: str | None = Query(default=None),
    region: str | None = Query(default=None),
    lead_tier: Literal["hot", "warm", "low"] | None = Query(default=None),
    latest_team_action: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> PagedCompanyLeads:
    items, total = CompanyLeadService(db, ctx).list(
        sector=sector,
        region=region,
        lead_tier=lead_tier,
        latest_team_action=latest_team_action,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return PagedCompanyLeads(
        items=items,
        page=Page(limit=limit, offset=offset, total=total),
    )


@router.get("/{company_id}", response_model=CompanyLeadDetail)
def get_company_lead(
    company_id: UUID,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> CompanyLeadDetail:
    return CompanyLeadService(db, ctx).detail(company_id)
