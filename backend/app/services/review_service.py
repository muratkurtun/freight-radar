from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import ReviewStatus
from app.domain.models import DetectedSignal, SignalReview
from app.domain.schemas import SignalRead
from app.domain.types import ReviewAction
from app.repositories.reviews import ReviewRepository
from app.repositories.signals import SignalRepository
from app.security.tenant_context import TenantContext


class ReviewService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.signals = SignalRepository(db, ctx.tenant_id)
        self.reviews = ReviewRepository(db, ctx.tenant_id)

    def list_pending(self, *, limit: int = 50, offset: int = 0) -> tuple[list[SignalRead], int]:
        items, total = self.signals.list_filtered(
            review_status=ReviewStatus.PENDING_REVIEW, limit=limit, offset=offset
        )
        return [SignalRead.model_validate(s) for s in items], total

    def approve(self, signal_id: UUID) -> SignalRead:
        signal = self.signals.get_or_404(signal_id)
        self._guard_pending(signal)
        return self._record(signal, "approve", ReviewStatus.APPROVED, reason=None)

    def reject(self, signal_id: UUID, reason: str) -> SignalRead:
        signal = self.signals.get_or_404(signal_id)
        self._guard_pending(signal)
        return self._record(signal, "reject", ReviewStatus.REJECTED, reason=reason)

    def _record(
        self,
        signal: DetectedSignal,
        action: ReviewAction,
        new_status: ReviewStatus,
        *,
        reason: str | None,
    ) -> SignalRead:
        review = SignalReview(
            tenant_id=self.ctx.tenant_id,
            detected_signal_id=signal.id,
            reviewer_user_id=self.ctx.user_id,
            action=action,
            reason=reason,
        )
        self.reviews.add(review)
        signal.review_status = new_status.value
        self.db.commit()
        self.db.refresh(signal)
        return SignalRead.model_validate(signal)

    @staticmethod
    def _guard_pending(signal: DetectedSignal) -> None:
        if signal.review_status != ReviewStatus.PENDING_REVIEW.value:
            raise AppError(
                f"Signal is already {signal.review_status}",
                code="invalid_state",
                status_code=409,
            )
