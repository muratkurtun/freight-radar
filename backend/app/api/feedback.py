"""Feedback / analytics endpoints (admin-only).

These fuel the prompt/keyword iteration loop: which signals were
rejected, approval rates sliced by signal_type and by source."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, require_tenant_admin
from app.domain.enums import SignalType
from app.domain.schemas import (
    ApprovalStatsByTypeRead,
    ApprovalStatsBySourceRead,
    FalsePositiveRead,
)
from app.security.tenant_context import TenantContext
from app.services.feedback_service import FeedbackService

router = APIRouter(
    prefix="/feedback",
    tags=["feedback"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("/false-positives", response_model=list[FalsePositiveRead])
def false_positives(
    signal_type: SignalType | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> list[FalsePositiveRead]:
    return FeedbackService(db, ctx).false_positives(signal_type=signal_type, limit=limit)


@router.get("/stats/by-signal-type", response_model=list[ApprovalStatsByTypeRead])
def stats_by_signal_type(
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> list[ApprovalStatsByTypeRead]:
    return FeedbackService(db, ctx).stats_by_signal_type()


@router.get("/stats/by-source", response_model=list[ApprovalStatsBySourceRead])
def stats_by_source(
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> list[ApprovalStatsBySourceRead]:
    return FeedbackService(db, ctx).stats_by_source()
