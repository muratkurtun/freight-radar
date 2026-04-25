"""Review endpoints for tenant admins.

Two routes:
  GET  /reviews/pending             -> paged list of pending signals
  POST /reviews/{detected_signal_id} -> approve or reject decision

The legacy singular `/review/...` router is preserved separately for
backward compatibility; new clients (Angular) should use this one."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, require_tenant_admin
from app.domain.schemas import (
    Page,
    PagedSignals,
    ReviewDecisionRequest,
    SignalRead,
)
from app.security.tenant_context import TenantContext
from app.services.review_service import ReviewService

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("/pending", response_model=PagedSignals)
def list_pending(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> PagedSignals:
    items, total = ReviewService(db, ctx).list_pending(limit=limit, offset=offset)
    return PagedSignals(items=items, page=Page(limit=limit, offset=offset, total=total))


@router.post("/{detected_signal_id}", response_model=SignalRead)
def decide(
    detected_signal_id: UUID,
    payload: ReviewDecisionRequest,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> SignalRead:
    service = ReviewService(db, ctx)
    if payload.action == "approve":
        return service.approve(detected_signal_id)
    # model_validator guarantees reason is set for reject
    assert payload.reason is not None
    return service.reject(detected_signal_id, payload.reason)
