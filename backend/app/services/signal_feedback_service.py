"""Service layer for signal_feedback.

Append-only by design (history preservation): every call to `submit`
inserts a new row, and the 'current team status' on a signal is
derived at read time from MAX(created_at). The service layer's job
here is mostly tenant + permission scoping; validation lives in the
Pydantic schema (see FeedbackCreate.model_validator)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.models import SignalFeedback
from app.domain.schemas import FeedbackCreate
from app.repositories.signal_feedback import SignalFeedbackRepository
from app.security.tenant_context import TenantContext


class SignalFeedbackService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.repo = SignalFeedbackRepository(db, ctx.tenant_id)

    def submit(self, signal_id: UUID, payload: FeedbackCreate) -> SignalFeedback:
        if not self.repo.signal_belongs_to_tenant(signal_id):
            # Same response regardless of whether the signal exists in
            # another tenant or doesn't exist at all — don't leak
            # cross-tenant existence.
            raise NotFoundError(f"Signal {signal_id} not found")
        feedback = SignalFeedback(
            tenant_id=self.ctx.tenant_id,
            signal_id=signal_id,
            user_id=self.ctx.user_id,
            action=payload.action.value,
            reason=payload.reason.value if payload.reason else None,
            note=payload.note,
        )
        self.repo.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def history(self, signal_id: UUID) -> list[SignalFeedback]:
        if not self.repo.signal_belongs_to_tenant(signal_id):
            raise NotFoundError(f"Signal {signal_id} not found")
        return self.repo.list_for_signal(signal_id)
