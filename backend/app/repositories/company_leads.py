"""Read-only company-lead aggregation.

The list / detail endpoints sit on top of one Postgres query. The
query rolls up every approved signal for the company plus the
tenant's signal_feedback rows and emits the lead-summary fields the
API exposes, including:

  - `highest_lead_score` (confidence-derived; see the model fallback
    note in schemas.py)
  - `lead_tier` (hot/warm/low thresholds from product spec)
  - `latest_team_action` — priority-derived status:
        converted > contacted > qualified > relevant >
        (dismissed | not_relevant) > new
    The label "latest" matches the API field name; mechanically it is
    the priority-derived team status, not the timestamp-most-recent
    action. The actual timestamp ships separately in `latest_feedback_at`.

Tenant scoping
--------------
Every CTE filters by :tenant_id on both `detected_signals` and
`signal_feedback`, so the cross-tenant probe is impossible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


# --------------------------------------------------------------------------
# Pure-Python specs for the SQL CASE expressions
#
# The aggregation SQL below uses CASE statements for two derived values:
# the priority-driven team status (converted > contacted > qualified >
# relevant > dismissed/not_relevant > new) and the lead score / tier.
# These helpers are the canonical spec — if you change either, change
# both. Tests target the helpers; an integration test against Postgres
# is the only way to lock the SQL to the same answers.
# --------------------------------------------------------------------------


def derive_team_status(
    *,
    converted_count: int,
    contacted_count: int,
    qualified_count: int,
    relevant_count: int,
    dismissed_count: int,
    not_relevant_count: int,
    wrong_company_count: int = 0,
    wrong_sector_count: int = 0,
    not_a_logistics_lead_count: int = 0,
) -> str:
    """Company-level current status from a feedback breakdown.

    Priority order matches the spec in this module's docstring. Among
    the negatives, `dismissed` wins ties / outright majority over the
    not-relevant cluster (`not_relevant` plus the corrective wrong_*
    actions). Empty breakdown → 'new'.
    """
    if converted_count > 0:
        return "converted"
    if contacted_count > 0:
        return "contacted"
    if qualified_count > 0:
        return "qualified"
    if relevant_count > 0:
        return "relevant"
    not_relevant_cluster = (
        not_relevant_count
        + wrong_company_count
        + wrong_sector_count
        + not_a_logistics_lead_count
    )
    if dismissed_count == 0 and not_relevant_cluster == 0:
        return "new"
    if dismissed_count >= not_relevant_cluster and dismissed_count > 0:
        return "dismissed"
    return "not_relevant"


def derive_lead_score(
    *,
    max_signal_score: int,
    recent_signal_count: int,
) -> int:
    """Company highest lead score from per-signal max + a 30-day bonus.

    Mirrors the SQL: `LEAST(100, max_signal_score + (recent>=2 ? 10 : 0))`.
    Returns 0 when the company has no signals (max=0)."""
    bonus = 10 if recent_signal_count >= 2 else 0
    return min(100, max(0, max_signal_score) + bonus)


def derive_lead_tier(score: int) -> str:
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "low"


# --------------------------------------------------------------------------
# Row dataclasses (kept lean — the schema layer fans these out into the
# API DTOs).
# --------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True, frozen=True)
class CompanyLeadAggregateRow:
    company_id: UUID
    company_name: str
    normalized_name: str
    sector: str | None
    region: str | None
    website: str | None
    signal_count: int
    latest_signal_date: datetime
    top_signal_type: str | None
    highest_lead_score: int
    lead_tier: str
    recommended_services: list[str]
    latest_detected_event: str | None
    suggested_next_action: str | None
    latest_team_action: str
    latest_feedback_at: datetime | None
    relevant_count: int
    qualified_count: int
    contacted_count: int
    converted_count: int
    dismissed_count: int
    not_relevant_count: int
    wrong_company_count: int
    wrong_sector_count: int
    not_a_logistics_lead_count: int
    total_feedback: int


@dataclass(slots=True, kw_only=True, frozen=True)
class CompanyLeadRelatedSignalRow:
    signal_id: UUID
    signal_type: str
    detected_event: str | None
    potential_logistics_need: str | None
    recommended_services: list[str]
    confidence: Decimal
    lead_score: int
    lead_tier: str
    urgency: str | None
    source_name: str
    source_url: str | None
    suggested_outreach_message: str | None
    created_at: datetime
    current_team_action: str | None
    latest_feedback_at: datetime | None


# --------------------------------------------------------------------------
# Aggregation SQL
# --------------------------------------------------------------------------

_BASE_AGG_SQL = """
WITH signal_agg AS (
    SELECT
        s.company_id                                       AS company_id,
        COUNT(*)                                           AS signal_count,
        MAX(s.created_at)                                  AS latest_signal_date,
        MAX(ROUND((s.confidence * 100)::numeric))::int     AS max_signal_score,
        COUNT(*) FILTER (
            WHERE s.created_at > now() - interval '30 days'
        )                                                  AS recent_signal_count
    FROM detected_signals s
    WHERE s.tenant_id = :tenant_id
      AND s.review_status = 'approved'
      AND s.company_id IS NOT NULL
    GROUP BY s.company_id
),
top_signal AS (
    SELECT DISTINCT ON (s.company_id)
        s.company_id,
        s.signal_type AS top_signal_type
    FROM detected_signals s
    WHERE s.tenant_id = :tenant_id
      AND s.review_status = 'approved'
      AND s.company_id IS NOT NULL
    ORDER BY s.company_id, s.confidence DESC NULLS LAST, s.created_at DESC
),
latest_signal AS (
    SELECT DISTINCT ON (s.company_id)
        s.company_id,
        s.detected_event,
        s.suggested_sales_action,
        s.suggested_outreach_message,
        s.created_at AS signal_at
    FROM detected_signals s
    WHERE s.tenant_id = :tenant_id
      AND s.review_status = 'approved'
      AND s.company_id IS NOT NULL
    ORDER BY s.company_id, s.created_at DESC
),
services_agg AS (
    SELECT
        s.company_id,
        array_agg(DISTINCT svc) AS recommended_services
    FROM detected_signals s,
         unnest(coalesce(s.recommended_services, ARRAY[]::text[])) svc
    WHERE s.tenant_id = :tenant_id
      AND s.review_status = 'approved'
      AND s.company_id IS NOT NULL
    GROUP BY s.company_id
),
feedback_pivot AS (
    SELECT
        s.company_id,
        COUNT(*) FILTER (WHERE f.action = 'relevant')             AS relevant_count,
        COUNT(*) FILTER (WHERE f.action = 'qualified')            AS qualified_count,
        COUNT(*) FILTER (WHERE f.action = 'contacted')            AS contacted_count,
        COUNT(*) FILTER (WHERE f.action = 'converted')            AS converted_count,
        COUNT(*) FILTER (WHERE f.action = 'dismissed')            AS dismissed_count,
        COUNT(*) FILTER (WHERE f.action = 'not_relevant')         AS not_relevant_count,
        COUNT(*) FILTER (WHERE f.action = 'wrong_company')        AS wrong_company_count,
        COUNT(*) FILTER (WHERE f.action = 'wrong_sector')         AS wrong_sector_count,
        COUNT(*) FILTER (WHERE f.action = 'not_a_logistics_lead') AS nalla_count,
        COUNT(*)                                                  AS total_feedback,
        MAX(f.created_at)                                         AS latest_feedback_at
    FROM signal_feedback f
    JOIN detected_signals s ON s.id = f.signal_id
    WHERE f.tenant_id = :tenant_id
      AND s.tenant_id = :tenant_id
      AND s.company_id IS NOT NULL
    GROUP BY s.company_id
),
agg AS (
    SELECT
        c.id                                AS company_id,
        c.name                              AS company_name,
        c.normalized_name                   AS normalized_name,
        c.sector                            AS sector,
        c.region                            AS region,
        c.website                           AS website,
        sa.signal_count                     AS signal_count,
        sa.latest_signal_date               AS latest_signal_date,
        ts.top_signal_type                  AS top_signal_type,
        LEAST(
            100,
            coalesce(sa.max_signal_score, 0) +
            CASE WHEN coalesce(sa.recent_signal_count, 0) >= 2 THEN 10 ELSE 0 END
        )                                   AS highest_lead_score,
        ls.detected_event                   AS latest_detected_event,
        ls.suggested_sales_action           AS suggested_next_action,
        ls.suggested_outreach_message       AS latest_outreach_message,
        coalesce(svc.recommended_services, ARRAY[]::text[]) AS recommended_services,
        coalesce(fp.relevant_count, 0)      AS relevant_count,
        coalesce(fp.qualified_count, 0)     AS qualified_count,
        coalesce(fp.contacted_count, 0)     AS contacted_count,
        coalesce(fp.converted_count, 0)     AS converted_count,
        coalesce(fp.dismissed_count, 0)     AS dismissed_count,
        coalesce(fp.not_relevant_count, 0)  AS not_relevant_count,
        coalesce(fp.wrong_company_count, 0) AS wrong_company_count,
        coalesce(fp.wrong_sector_count, 0)  AS wrong_sector_count,
        coalesce(fp.nalla_count, 0)         AS not_a_logistics_lead_count,
        coalesce(fp.total_feedback, 0)      AS total_feedback,
        fp.latest_feedback_at               AS latest_feedback_at
    FROM companies c
    JOIN signal_agg sa ON sa.company_id = c.id
    LEFT JOIN top_signal ts     ON ts.company_id = c.id
    LEFT JOIN latest_signal ls  ON ls.company_id = c.id
    LEFT JOIN services_agg svc  ON svc.company_id = c.id
    LEFT JOIN feedback_pivot fp ON fp.company_id = c.id
    WHERE c.tenant_id = :tenant_id
)
SELECT
    company_id,
    company_name,
    normalized_name,
    sector,
    region,
    website,
    signal_count,
    latest_signal_date,
    top_signal_type,
    highest_lead_score,
    CASE
        WHEN highest_lead_score >= 75 THEN 'hot'
        WHEN highest_lead_score >= 50 THEN 'warm'
        ELSE 'low'
    END                                                              AS lead_tier,
    recommended_services,
    latest_detected_event,
    suggested_next_action,
    latest_outreach_message,
    relevant_count,
    qualified_count,
    contacted_count,
    converted_count,
    dismissed_count,
    not_relevant_count,
    wrong_company_count,
    wrong_sector_count,
    not_a_logistics_lead_count,
    total_feedback,
    latest_feedback_at,
    -- Priority-derived team status. The logic mirrors the spec in
    -- the docstring; keep this CASE in sync with the Python helper
    -- below if either is changed.
    CASE
        WHEN converted_count > 0  THEN 'converted'
        WHEN contacted_count > 0  THEN 'contacted'
        WHEN qualified_count > 0  THEN 'qualified'
        WHEN relevant_count  > 0  THEN 'relevant'
        WHEN total_feedback  > 0
            THEN CASE
                WHEN dismissed_count >=
                     (not_relevant_count + wrong_company_count
                      + wrong_sector_count + not_a_logistics_lead_count)
                  AND dismissed_count > 0
                THEN 'dismissed'
                ELSE 'not_relevant'
            END
        ELSE 'new'
    END                                                              AS latest_team_action
FROM agg
"""


_LIST_FILTERS_AND_PAGE = """
WHERE (:sector IS NULL OR sector = :sector)
  AND (:region IS NULL OR region = :region)
  AND (:lead_tier IS NULL OR
       CASE
         WHEN highest_lead_score >= 75 THEN 'hot'
         WHEN highest_lead_score >= 50 THEN 'warm'
         ELSE 'low'
       END = :lead_tier)
  AND (:latest_team_action IS NULL OR latest_team_action = :latest_team_action)
  AND (:min_score IS NULL OR highest_lead_score >= :min_score)
ORDER BY highest_lead_score DESC, latest_signal_date DESC NULLS LAST
LIMIT :limit OFFSET :offset
"""


_LIST_SQL = text(
    f"""
    SELECT * FROM (
        {_BASE_AGG_SQL}
    ) leads
    {_LIST_FILTERS_AND_PAGE}
    """
)


_COUNT_SQL = text(
    f"""
    SELECT COUNT(*) FROM (
        {_BASE_AGG_SQL}
    ) leads
    WHERE (:sector IS NULL OR sector = :sector)
      AND (:region IS NULL OR region = :region)
      AND (:lead_tier IS NULL OR
           CASE
             WHEN highest_lead_score >= 75 THEN 'hot'
             WHEN highest_lead_score >= 50 THEN 'warm'
             ELSE 'low'
           END = :lead_tier)
      AND (:latest_team_action IS NULL OR latest_team_action = :latest_team_action)
      AND (:min_score IS NULL OR highest_lead_score >= :min_score)
    """
)


_DETAIL_SQL = text(
    f"""
    SELECT * FROM (
        {_BASE_AGG_SQL}
    ) leads
    WHERE company_id = :company_id
    """
)


_RELATED_SIGNALS_SQL = text(
    """
    SELECT
        s.id                              AS signal_id,
        s.signal_type                     AS signal_type,
        s.detected_event                  AS detected_event,
        s.potential_logistics_need        AS potential_logistics_need,
        coalesce(s.recommended_services,
                 ARRAY[]::text[])         AS recommended_services,
        s.confidence                      AS confidence,
        ROUND((s.confidence * 100)::numeric)::int AS lead_score,
        CASE
            WHEN ROUND((s.confidence * 100)::numeric)::int >= 75 THEN 'hot'
            WHEN ROUND((s.confidence * 100)::numeric)::int >= 50 THEN 'warm'
            ELSE 'low'
        END                               AS lead_tier,
        s.urgency                         AS urgency,
        src.name                          AS source_name,
        r.url                             AS source_url,
        s.suggested_outreach_message      AS suggested_outreach_message,
        s.created_at                      AS created_at,
        latest.action                     AS current_team_action,
        latest.created_at                 AS latest_feedback_at
    FROM detected_signals s
    JOIN raw_source_items r   ON r.id   = s.raw_source_item_id
    JOIN sources          src ON src.id = r.source_id
    LEFT JOIN LATERAL (
        SELECT f.action, f.created_at
        FROM signal_feedback f
        WHERE f.signal_id = s.id
          AND f.tenant_id = :tenant_id
        ORDER BY f.created_at DESC
        LIMIT 1
    ) latest ON TRUE
    WHERE s.tenant_id     = :tenant_id
      AND s.review_status = 'approved'
      AND s.company_id    = :company_id
    ORDER BY s.created_at DESC
    """
)


# --------------------------------------------------------------------------
# Repository
# --------------------------------------------------------------------------


def _row_to_aggregate(row) -> CompanyLeadAggregateRow:
    return CompanyLeadAggregateRow(
        company_id=row["company_id"],
        company_name=row["company_name"],
        normalized_name=row["normalized_name"],
        sector=row["sector"],
        region=row["region"],
        website=row["website"],
        signal_count=int(row["signal_count"]),
        latest_signal_date=row["latest_signal_date"],
        top_signal_type=row["top_signal_type"],
        highest_lead_score=int(row["highest_lead_score"]),
        lead_tier=row["lead_tier"],
        recommended_services=list(row["recommended_services"] or []),
        latest_detected_event=row["latest_detected_event"],
        suggested_next_action=row["suggested_next_action"],
        latest_team_action=row["latest_team_action"],
        latest_feedback_at=row["latest_feedback_at"],
        relevant_count=int(row["relevant_count"]),
        qualified_count=int(row["qualified_count"]),
        contacted_count=int(row["contacted_count"]),
        converted_count=int(row["converted_count"]),
        dismissed_count=int(row["dismissed_count"]),
        not_relevant_count=int(row["not_relevant_count"]),
        wrong_company_count=int(row["wrong_company_count"]),
        wrong_sector_count=int(row["wrong_sector_count"]),
        not_a_logistics_lead_count=int(row["not_a_logistics_lead_count"]),
        total_feedback=int(row["total_feedback"]),
    )


class CompanyLeadRepository:
    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def list(
        self,
        *,
        sector: str | None = None,
        region: str | None = None,
        lead_tier: str | None = None,
        latest_team_action: str | None = None,
        min_score: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[CompanyLeadAggregateRow], int]:
        params = {
            "tenant_id": self.tenant_id,
            "sector": sector,
            "region": region,
            "lead_tier": lead_tier,
            "latest_team_action": latest_team_action,
            "min_score": min_score,
            "limit": limit,
            "offset": offset,
        }
        rows = self.db.execute(_LIST_SQL, params).mappings().all()
        total = int(
            self.db.execute(
                _COUNT_SQL,
                {k: v for k, v in params.items() if k not in ("limit", "offset")},
            ).scalar_one()
        )
        return [_row_to_aggregate(r) for r in rows], total

    def detail(self, company_id: UUID) -> CompanyLeadAggregateRow | None:
        row = (
            self.db.execute(
                _DETAIL_SQL,
                {"tenant_id": self.tenant_id, "company_id": company_id},
            )
            .mappings()
            .first()
        )
        return _row_to_aggregate(row) if row else None

    def related_signals(
        self, company_id: UUID
    ) -> list[CompanyLeadRelatedSignalRow]:
        rows = self.db.execute(
            _RELATED_SIGNALS_SQL,
            {"tenant_id": self.tenant_id, "company_id": company_id},
        ).mappings().all()
        return [
            CompanyLeadRelatedSignalRow(
                signal_id=r["signal_id"],
                signal_type=r["signal_type"],
                detected_event=r["detected_event"],
                potential_logistics_need=r["potential_logistics_need"],
                recommended_services=list(r["recommended_services"] or []),
                confidence=r["confidence"],
                lead_score=int(r["lead_score"]),
                lead_tier=r["lead_tier"],
                urgency=r["urgency"],
                source_name=r["source_name"],
                source_url=r["source_url"],
                suggested_outreach_message=r["suggested_outreach_message"],
                created_at=r["created_at"],
                current_team_action=r["current_team_action"],
                latest_feedback_at=r["latest_feedback_at"],
            )
            for r in rows
        ]
