from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.enums import ReviewStatus, SignalType, SourceType
from app.domain.schemas import SignalDetail, SignalRead, SignalReviewRead
from app.repositories.reviews import ReviewRepository
from app.repositories.signals import SignalRepository
from app.security.tenant_context import TenantContext


class SignalService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.signals = SignalRepository(db, ctx.tenant_id)
        self.reviews = ReviewRepository(db, ctx.tenant_id)

    def list(
        self,
        *,
        signal_type: SignalType | None = None,
        review_status: ReviewStatus | None = None,
        source_type: SourceType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SignalRead], int]:
        items, total = self.signals.list_filtered(
            signal_type=signal_type,
            review_status=review_status,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )
        return [SignalRead.model_validate(s) for s in items], total

    def detail(self, signal_id: UUID) -> SignalDetail:
        row = self.signals.get_with_raw(signal_id)
        if row is None:
            raise NotFoundError(f"Signal {signal_id} not found")
        signal, raw = row
        latest = self.reviews.latest_for_signal(signal.id)
        return SignalDetail(
            **SignalRead.model_validate(signal).model_dump(),
            raw_title=raw.title,
            raw_url=raw.url,
            raw_content=raw.content,
            latest_review=SignalReviewRead.model_validate(latest) if latest else None,
        )
