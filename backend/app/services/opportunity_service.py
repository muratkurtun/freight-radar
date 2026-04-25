"""Read-only service for the approved-signals ("opportunity") list.

Thin wrapper over OpportunityQueryRepository — kept as a service so
routers have one consistent shape to call into and tenant scoping flows
through TenantContext."""
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
                signal_type=SignalType(row.signal_type),
                confidence=row.confidence,
                company_name=row.company_name,
                location=row.location,
                role_title=row.role_title,
                supplier_name=row.supplier_name,
                summary=row.summary,
                created_at=row.created_at,
                raw_title=row.raw_title,
                raw_url=row.raw_url,
                published_at=row.published_at,
                source_id=row.source_id,
                source_name=row.source_name,
                source_type=SourceType(row.source_type),
            )
            for row in rows
        ], total
