"""Review repository — signal_reviews table.

Event log of approve/reject actions. The denormalized
`detected_signals.review_status` column is the "current state"; this
table is the history. A signal can only be reviewed once under the
current guard (see ReviewService._guard_pending), but the schema is
append-only so we can lift that restriction later without losing prior
decisions."""
from __future__ import annotations

from uuid import UUID

from app.domain.models import SignalReview
from app.domain.types import ReviewAction
from app.repositories.base import TenantAwareRepository


class ReviewRepository(TenantAwareRepository[SignalReview]):
    model = SignalReview

    def latest_for_signal(self, detected_signal_id: UUID) -> SignalReview | None:
        stmt = (
            self._base_query()
            .where(SignalReview.detected_signal_id == detected_signal_id)
            .order_by(SignalReview.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_signal(self, detected_signal_id: UUID) -> list[SignalReview]:
        stmt = (
            self._base_query()
            .where(SignalReview.detected_signal_id == detected_signal_id)
            .order_by(SignalReview.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def record(
        self,
        *,
        detected_signal_id: UUID,
        reviewer_user_id: UUID,
        action: ReviewAction,
        reason: str | None,
    ) -> SignalReview:
        review = SignalReview(
            tenant_id=self.tenant_id,
            detected_signal_id=detected_signal_id,
            reviewer_user_id=reviewer_user_id,
            action=action,
            reason=reason,
        )
        return self.add(review)
