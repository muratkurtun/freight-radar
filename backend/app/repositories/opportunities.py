"""Opportunity read-model — the list sales users see.

An "opportunity" is an approved DetectedSignal presented with the raw
item and source context needed for outreach. This repo is READ ONLY
and lives separately from SignalRepository because:

  - its queries always join three tables (signal + raw + source);
  - it is only ever called from user-facing list endpoints;
  - SQL here is clearer than a Core expression tree.
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
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None
    created_at: datetime
    raw_title: str | None
    raw_url: str | None
    published_at: datetime | None
    source_id: UUID
    source_name: str
    source_type: str


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
        s.created_at      AS created_at,
        r.title           AS raw_title,
        r.url             AS raw_url,
        r.published_at    AS published_at,
        src.id            AS source_id,
        src.name          AS source_name,
        src.source_type   AS source_type
    FROM detected_signals s
    JOIN raw_source_items r   ON r.id   = s.raw_source_item_id
    JOIN sources          src ON src.id = r.source_id
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
        return [OpportunityRow(**dict(row)) for row in rows], total
