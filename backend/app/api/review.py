from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, require_tenant_admin
from app.domain.schemas import PagedSignals, Page, RejectRequest, SignalRead
from app.security.tenant_context import TenantContext
from app.services.review_service import ReviewService

router = APIRouter(
    prefix="/review",
    tags=["review"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("/queue", response_model=PagedSignals)
def review_queue(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> PagedSignals:
    items, total = ReviewService(db, ctx).list_pending(limit=limit, offset=offset)
    return PagedSignals(items=items, page=Page(limit=limit, offset=offset, total=total))


@router.post("/{signal_id}/approve", response_model=SignalRead)
def approve(
    signal_id: UUID,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> SignalRead:
    return ReviewService(db, ctx).approve(signal_id)


@router.post("/{signal_id}/reject", response_model=SignalRead)
def reject(
    signal_id: UUID,
    payload: RejectRequest,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> SignalRead:
    return ReviewService(db, ctx).reject(signal_id, payload.reason)
