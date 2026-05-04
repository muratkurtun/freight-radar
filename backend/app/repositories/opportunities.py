"""Opportunity read-model — the list sales users see.

An "opportunity" is an approved DetectedSignal presented with the raw
item, source context, the v2 logistics-lead fields, and team feedback
aggregates needed for outreach.

Read-only. Lives separately from SignalRepository because:
  - its queries always join three tables (signal + raw + source) and a
    LATERAL subquery for the latest feedback;
  - it's only ever called from user-facing list endpoints;
  - SQL here is clearer than a Core expression tree once the joins +
    array columns + aggregates are involved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.enums import SignalType


@dataclass(slots=True, kw_only=True, frozen=True)
class OpportunityRow:
    signal_id: UUID
    signal_type: str
    confidence: Decimal

    # Pre-pivot fields (legacy rows only).
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None

    # v2 logistics-lead fields.
    target_customer_type: str | None
    sector: str | None
    region: str | None
    detected_event: str | None
    why_relevant_for_logistics: str | None
    potential_logistics_need: str | None
    recommended_services: list[str]
    urgency: str | None
    suggested_sales_action: str | None
    suggested_outreach_message: str | None
    evidence_snippet: str | None

    created_at: datetime
    raw_title: str | None
    raw_url: str | None
    published_at: datetime | None
    source_id: UUID
    source_name: str
    source_type: str

    # Team feedback aggregates (NULL when the signal has no feedback yet).
    feedback_count: int
    last_feedback_action: str | None
    last_feedback_at: datetime | None
    last_feedback_user_id: UUID | None


# Two correlated subqueries against signal_feedback per row:
#   - feedback_count = COUNT(*)
#   - latest_* fields from a LATERAL "ORDER BY created_at DESC LIMIT 1"
# LATERAL keeps the planner from materializing the whole feedback table
# for every row; the (signal_id, created_at DESC) index serves both.
_LIST_SQL = text(
    """
    SELECT
        s.id              AS signal_id,
        s.signal_type     AS signal_type,
        s.confidence      AS confidence,
        s.company_name    AS company_name,
        s.location        AS location,
        s.role_title      AS role_title,
        s.supplier_name   AS supplier_name,
        s.summary         AS summary,
        s.target_customer_type        AS target_customer_type,
        s.sector                      AS sector,
        s.region                      AS region,
        s.detected_event              AS detected_event,
        s.why_relevant_for_logistics  AS why_relevant_for_logistics,
        s.potential_logistics_need    AS potential_logistics_need,
        s.recommended_services        AS recommended_services,
        s.urgency                     AS urgency,
        s.suggested_sales_action      AS suggested_sales_action,
        s.suggested_outreach_message  AS suggested_outreach_message,
        s.evidence_snippet            AS evidence_snippet,
        s.created_at      AS created_at,
        r.title           AS raw_title,
        r.url             AS raw_url,
        r.published_at    AS published_at,
        src.id            AS source_id,
        src.name          AS source_name,
        src.source_type   AS source_type,
        COALESCE(fc.cnt, 0)        AS feedback_count,
        latest.action              AS last_feedback_action,
        latest.created_at          AS last_feedback_at,
        latest.user_id             AS last_feedback_user_id
    FROM detected_signals s
    JOIN raw_source_items r   ON r.id   = s.raw_source_item_id
    JOIN sources          src ON src.id = r.source_id
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS cnt
        FROM signal_feedback f
        WHERE f.signal_id = s.id
          AND f.tenant_id = :tenant_id
    ) fc ON TRUE
    LEFT JOIN LATERAL (
        SELECT f.action, f.created_at, f.user_id
        FROM signal_feedback f
        WHERE f.signal_id = s.id
          AND f.tenant_id = :tenant_id
        ORDER BY f.created_at DESC
        LIMIT 1
    ) latest ON TRUE
    WHERE s.tenant_id     = :tenant_id
      AND s.review_status = 'approved'
      AND (:signal_type IS NULL OR s.signal_type = :signal_type)
      AND (:since       IS NULL OR s.created_at >= :since)
    ORDER BY s.created_at DESC
    LIMIT :limit OFFSET :offset
    """
)

_COUNT_SQL = text(
    """
    SELECT COUNT(*)
    FROM detected_signals s
    WHERE s.tenant_id     = :tenant_id
      AND s.review_status = 'approved'
      AND (:signal_type IS NULL OR s.signal_type = :signal_type)
      AND (:since       IS NULL OR s.created_at >= :since)
    """
)


class OpportunityQueryRepository:
    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def list(
        self,
        *,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OpportunityRow], int]:
        params = {
            "tenant_id": self.tenant_id,
            "signal_type": signal_type.value if signal_type else None,
            "since": since,
            "limit": limit,
            "offset": offset,
        }
        rows = self.db.execute(_LIST_SQL, params).mappings().all()
        total = int(
            self.db.execute(
                _COUNT_SQL,
                {k: params[k] for k in ("tenant_id", "signal_type", "since")},
            ).scalar_one()
        )
        return [
            OpportunityRow(
                signal_id=row["signal_id"],
                signal_type=row["signal_type"],
                confidence=row["confidence"],
                company_name=row["company_name"],
                location=row["location"],
                role_title=row["role_title"],
                supplier_name=row["supplier_name"],
                summary=row["summary"],
                target_customer_type=row["target_customer_type"],
                sector=row["sector"],
                region=row["region"],
                detected_event=row["detected_event"],
                why_relevant_for_logistics=row["why_relevant_for_logistics"],
                potential_logistics_need=row["potential_logistics_need"],
                recommended_services=list(row["recommended_services"] or []),
                urgency=row["urgency"],
                suggested_sales_action=row["suggested_sales_action"],
                suggested_outreach_message=row["suggested_outreach_message"],
                evidence_snippet=row["evidence_snippet"],
                created_at=row["created_at"],
                raw_title=row["raw_title"],
                raw_url=row["raw_url"],
                published_at=row["published_at"],
                source_id=row["source_id"],
                source_name=row["source_name"],
                source_type=row["source_type"],
                feedback_count=int(row["feedback_count"]),
                last_feedback_action=row["last_feedback_action"],
                last_feedback_at=row["last_feedback_at"],
                last_feedback_user_id=row["last_feedback_user_id"],
            )
            for row in rows
        ], total
