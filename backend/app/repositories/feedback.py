"""Feedback repository — detector-quality analytics over the review log.

Answers two kinds of questions the platform needs for prompt / keyword
iteration:

  1. "Which specific signals did reviewers reject, and why?"
      -> false_positive_examples()

  2. "What is the approval rate of our classifier, sliced by ...?"
      -> approval_rate_by_signal_type()
      -> approval_rate_by_prompt_version()
      -> approval_rate_by_source()

All queries are read-only and tenant-scoped."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.enums import SignalType


@dataclass(slots=True, kw_only=True, frozen=True)
class FalsePositiveExample:
    signal_id: UUID
    signal_type: str
    confidence: Decimal
    prompt_version: str
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None
    reject_reason: str
    rejected_at: datetime
    raw_title: str | None
    raw_url: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalStats:
    approved: int
    rejected: int
    pending: int
    total: int

    @property
    def approval_rate(self) -> float:
        decided = self.approved + self.rejected
        return self.approved / decided if decided else 0.0


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalStatsByType:
    signal_type: str
    stats: ApprovalStats


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalStatsByPromptVersion:
    prompt_version: str
    stats: ApprovalStats


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalStatsBySource:
    source_id: UUID
    source_name: str
    source_type: str
    stats: ApprovalStats


_FALSE_POSITIVES_SQL = text(
    """
    SELECT
        s.id              AS signal_id,
        s.signal_type     AS signal_type,
        s.confidence      AS confidence,
        s.prompt_version  AS prompt_version,
        s.company_name    AS company_name,
        s.location        AS location,
        s.role_title      AS role_title,
        s.supplier_name   AS supplier_name,
        s.summary         AS summary,
        rv.reason         AS reject_reason,
        rv.created_at     AS rejected_at,
        ri.title          AS raw_title,
        ri.url            AS raw_url
    FROM detected_signals s
    JOIN signal_reviews   rv ON rv.detected_signal_id = s.id
    JOIN raw_source_items ri ON ri.id                 = s.raw_source_item_id
    WHERE s.tenant_id     = :tenant_id
      AND s.review_status = 'rejected'
      AND rv.action       = 'reject'
      AND (:signal_type IS NULL OR s.signal_type = :signal_type)
    ORDER BY rv.created_at DESC
    LIMIT :limit
    """
)

_STATS_BY_TYPE_SQL = text(
    """
    SELECT
        signal_type,
        COUNT(*) FILTER (WHERE review_status = 'approved')       AS approved,
        COUNT(*) FILTER (WHERE review_status = 'rejected')       AS rejected,
        COUNT(*) FILTER (WHERE review_status = 'pending_review') AS pending,
        COUNT(*)                                                 AS total
    FROM detected_signals
    WHERE tenant_id = :tenant_id
    GROUP BY signal_type
    ORDER BY total DESC
    """
)

_STATS_BY_PROMPT_VERSION_SQL = text(
    """
    SELECT
        prompt_version,
        COUNT(*) FILTER (WHERE review_status = 'approved')       AS approved,
        COUNT(*) FILTER (WHERE review_status = 'rejected')       AS rejected,
        COUNT(*) FILTER (WHERE review_status = 'pending_review') AS pending,
        COUNT(*)                                                 AS total
    FROM detected_signals
    WHERE tenant_id = :tenant_id
    GROUP BY prompt_version
    ORDER BY prompt_version DESC
    """
)

_STATS_BY_SOURCE_SQL = text(
    """
    -- Drive the aggregation from raw_source_items so that platform pool
    -- sources (sources.tenant_id IS NULL) are picked up via the tenant's
    -- own raw rows. Pre-0004 the query started from `sources` filtered
    -- by src.tenant_id; that path no longer reaches platform rows.
    SELECT
        src.id            AS source_id,
        src.name          AS source_name,
        src.source_type   AS source_type,
        COUNT(s.id) FILTER (WHERE s.review_status = 'approved')       AS approved,
        COUNT(s.id) FILTER (WHERE s.review_status = 'rejected')       AS rejected,
        COUNT(s.id) FILTER (WHERE s.review_status = 'pending_review') AS pending,
        COUNT(s.id)                                                   AS total
    FROM raw_source_items ri
    JOIN sources           src ON src.id = ri.source_id
    LEFT JOIN detected_signals s
        ON s.raw_source_item_id = ri.id
       AND s.tenant_id          = :tenant_id
    WHERE ri.tenant_id = :tenant_id
    GROUP BY src.id, src.name, src.source_type
    ORDER BY total DESC
    """
)


class FeedbackRepository:
    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def false_positive_examples(
        self,
        *,
        signal_type: SignalType | None = None,
        limit: int = 20,
    ) -> list[FalsePositiveExample]:
        rows = self.db.execute(
            _FALSE_POSITIVES_SQL,
            {
                "tenant_id": self.tenant_id,
                "signal_type": signal_type.value if signal_type else None,
                "limit": limit,
            },
        ).mappings().all()
        return [FalsePositiveExample(**dict(row)) for row in rows]

    def approval_rate_by_signal_type(self) -> list[ApprovalStatsByType]:
        rows = self.db.execute(
            _STATS_BY_TYPE_SQL, {"tenant_id": self.tenant_id}
        ).mappings().all()
        return [
            ApprovalStatsByType(
                signal_type=row["signal_type"],
                stats=_stats_from_row(row),
            )
            for row in rows
        ]

    def approval_rate_by_prompt_version(self) -> list[ApprovalStatsByPromptVersion]:
        rows = self.db.execute(
            _STATS_BY_PROMPT_VERSION_SQL, {"tenant_id": self.tenant_id}
        ).mappings().all()
        return [
            ApprovalStatsByPromptVersion(
                prompt_version=row["prompt_version"],
                stats=_stats_from_row(row),
            )
            for row in rows
        ]

    def approval_rate_by_source(self) -> list[ApprovalStatsBySource]:
        rows = self.db.execute(
            _STATS_BY_SOURCE_SQL, {"tenant_id": self.tenant_id}
        ).mappings().all()
        return [
            ApprovalStatsBySource(
                source_id=row["source_id"],
                source_name=row["source_name"],
                source_type=row["source_type"],
                stats=_stats_from_row(row),
            )
            for row in rows
        ]


def _stats_from_row(row: dict) -> ApprovalStats:
    return ApprovalStats(
        approved=int(row["approved"] or 0),
        rejected=int(row["rejected"] or 0),
        pending=int(row["pending"] or 0),
        total=int(row["total"] or 0),
    )
