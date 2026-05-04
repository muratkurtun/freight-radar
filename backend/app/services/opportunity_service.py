"""Read-only service for the approved-signals ("opportunity") list.

Thin wrapper over OpportunityQueryRepository. Maps the SQL row to the
HTTP DTO. signal_type and source_type are passed through as strings
(the schema accepts str on read paths) so legacy pre-0005 values
deserialize without raising.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain.enums import SignalType, SourceType
from app.domain.schemas import OpportunityRead
from app.repositories.opportunities import OpportunityQueryRepository
from app.security.tenant_context import TenantContext


class OpportunityService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.repo = OpportunityQueryRepository(db, ctx.tenant_id)

    def list(
        self,
        *,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[OpportunityRead], int]:
        rows, total = self.repo.list(
            signal_type=signal_type,
            since=since,
            limit=limit,
            offset=offset,
        )
        return [
            OpportunityRead(
                signal_id=row.signal_id,
                signal_type=row.signal_type,
                confidence=row.confidence,
                company_name=row.company_name,
                # Legacy fields
                location=row.location,
                role_title=row.role_title,
                supplier_name=row.supplier_name,
                summary=row.summary,
                # v2 logistics-lead fields
                target_customer_type=row.target_customer_type,
                sector=row.sector,
                region=row.region,
                detected_event=row.detected_event,
                why_relevant_for_logistics=row.why_relevant_for_logistics,
                potential_logistics_need=row.potential_logistics_need,
                recommended_services=row.recommended_services,
                urgency=row.urgency,
                suggested_sales_action=row.suggested_sales_action,
                suggested_outreach_message=row.suggested_outreach_message,
                evidence_snippet=row.evidence_snippet,
                created_at=row.created_at,
                raw_title=row.raw_title,
                raw_url=row.raw_url,
                published_at=row.published_at,
                source_id=row.source_id,
                source_name=row.source_name,
                source_type=SourceType(row.source_type),
                # Feedback aggregates
                feedback_count=row.feedback_count,
                last_feedback_action=row.last_feedback_action,
                last_feedback_at=row.last_feedback_at,
                last_feedback_user_id=row.last_feedback_user_id,
            )
            for row in rows
        ], total
