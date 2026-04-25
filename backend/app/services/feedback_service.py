"""Read-only service for detector-quality analytics.

Tenant-scoped wrapper over FeedbackRepository. Returns Pydantic models
so the router can hand them straight to the response."""
from sqlalchemy.orm import Session

from app.domain.enums import SignalType, SourceType
from app.domain.schemas import (
    ApprovalStatsByTypeRead,
    ApprovalStatsBySourceRead,
    ApprovalStatsRead,
    FalsePositiveRead,
)
from app.repositories.feedback import (
    ApprovalStats,
    FeedbackRepository,
)
from app.security.tenant_context import TenantContext


class FeedbackService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.repo = FeedbackRepository(db, ctx.tenant_id)

    def false_positives(
        self,
        *,
        signal_type: SignalType | None = None,
        limit: int = 20,
    ) -> list[FalsePositiveRead]:
        rows = self.repo.false_positive_examples(signal_type=signal_type, limit=limit)
        return [
            FalsePositiveRead(
                signal_id=row.signal_id,
                signal_type=SignalType(row.signal_type),
                confidence=row.confidence,
                prompt_version=row.prompt_version,
                company_name=row.company_name,
                location=row.location,
                role_title=row.role_title,
                supplier_name=row.supplier_name,
                summary=row.summary,
                reject_reason=row.reject_reason,
                rejected_at=row.rejected_at,
                raw_title=row.raw_title,
                raw_url=row.raw_url,
            )
            for row in rows
        ]

    def stats_by_signal_type(self) -> list[ApprovalStatsByTypeRead]:
        rows = self.repo.approval_rate_by_signal_type()
        return [
            ApprovalStatsByTypeRead(
                signal_type=SignalType(row.signal_type),
                stats=_to_stats_read(row.stats),
            )
            for row in rows
        ]

    def stats_by_source(self) -> list[ApprovalStatsBySourceRead]:
        rows = self.repo.approval_rate_by_source()
        return [
            ApprovalStatsBySourceRead(
                source_id=row.source_id,
                source_name=row.source_name,
                source_type=SourceType(row.source_type),
                stats=_to_stats_read(row.stats),
            )
            for row in rows
        ]


def _to_stats_read(stats: ApprovalStats) -> ApprovalStatsRead:
    return ApprovalStatsRead(
        approved=stats.approved,
        rejected=stats.rejected,
        pending=stats.pending,
        total=stats.total,
        approval_rate=stats.approval_rate,
    )
