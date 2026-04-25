from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, tenant_context
from app.domain.enums import ReviewStatus, SignalType, SourceType
from app.domain.schemas import PagedSignals, Page, SignalDetail
from app.security.tenant_context import TenantContext
from app.services.signal_service import SignalService

router = APIRouter(
    prefix="/signals",
    tags=["signals"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("", response_model=PagedSignals)
def list_signals(
    signal_type: SignalType | None = Query(default=None),
    review_status: ReviewStatus | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> PagedSignals:
    items, total = SignalService(db, ctx).list(
        signal_type=signal_type,
        review_status=review_status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return PagedSignals(items=items, page=Page(limit=limit, offset=offset, total=total))


@router.get("/{signal_id}", response_model=SignalDetail)
def get_signal(
    signal_id: UUID,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> SignalDetail:
    return SignalService(db, ctx).detail(signal_id)
