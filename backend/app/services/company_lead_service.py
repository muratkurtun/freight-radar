"""Read-only service for the company-lead view.

Maps the SQL aggregation rows to the API DTOs. Logic-light by design:
the SQL already produces the priority-derived `latest_team_action` and
the score / tier; this service just packages the row and pulls the
related-signals list for detail responses.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.schemas import (
    CompanyLeadDetail,
    CompanyLeadRelatedSignal,
    CompanyLeadSummary,
    FeedbackCounts,
)
from app.repositories.company_leads import (
    CompanyLeadAggregateRow,
    CompanyLeadRelatedSignalRow,
    CompanyLeadRepository,
)
from app.security.tenant_context import TenantContext


def _to_summary(row: CompanyLeadAggregateRow) -> CompanyLeadSummary:
    return CompanyLeadSummary(
        company_id=row.company_id,
        company_name=row.company_name,
        normalized_name=row.normalized_name,
        sector=row.sector,
        region=row.region,
        website=row.website,
        signal_count=row.signal_count,
        latest_signal_date=row.latest_signal_date,
        top_signal_type=row.top_signal_type,
        highest_lead_score=row.highest_lead_score,
        lead_tier=row.lead_tier,  # type: ignore[arg-type]
        recommended_services=row.recommended_services,
        latest_detected_event=row.latest_detected_event,
        suggested_next_action=row.suggested_next_action,
        latest_team_action=row.latest_team_action,  # type: ignore[arg-type]
        latest_feedback_at=row.latest_feedback_at,
        feedback_counts=FeedbackCounts(
            relevant=row.relevant_count,
            qualified=row.qualified_count,
            contacted=row.contacted_count,
            converted=row.converted_count,
            dismissed=row.dismissed_count,
            not_relevant=row.not_relevant_count,
            wrong_company=row.wrong_company_count,
            wrong_sector=row.wrong_sector_count,
            not_a_logistics_lead=row.not_a_logistics_lead_count,
            total=row.total_feedback,
        ),
    )


def _to_related(row: CompanyLeadRelatedSignalRow) -> CompanyLeadRelatedSignal:
    return CompanyLeadRelatedSignal(
        signal_id=row.signal_id,
        signal_type=row.signal_type,
        detected_event=row.detected_event,
        potential_logistics_need=row.potential_logistics_need,
        recommended_services=row.recommended_services,
        confidence=row.confidence,
        lead_score=row.lead_score,
        lead_tier=row.lead_tier,  # type: ignore[arg-type]
        urgency=row.urgency,
        source_name=row.source_name,
        source_url=row.source_url,
        suggested_outreach_message=row.suggested_outreach_message,
        created_at=row.created_at,
        current_team_action=row.current_team_action,
        latest_feedback_at=row.latest_feedback_at,
    )


class CompanyLeadService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.repo = CompanyLeadRepository(db, ctx.tenant_id)

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
    ) -> tuple[list[CompanyLeadSummary], int]:
        rows, total = self.repo.list(
            sector=sector,
            region=region,
            lead_tier=lead_tier,
            latest_team_action=latest_team_action,
            min_score=min_score,
            limit=limit,
            offset=offset,
        )
        return [_to_summary(r) for r in rows], total

    def detail(self, company_id: UUID) -> CompanyLeadDetail:
        row = self.repo.detail(company_id)
        if row is None:
            raise NotFoundError(f"Company {company_id} not found")
        signals = self.repo.related_signals(company_id)
        summary = _to_summary(row)
        # Return a CompanyLeadDetail by extending the summary's fields.
        return CompanyLeadDetail(
            **summary.model_dump(),
            related_signals=[_to_related(s) for s in signals],
        )
