"""Repository for signal_feedback (sales-team feedback history).

Tenant-scoped via TenantAwareRepository. The table is append-only so
this repo exposes `add` for writes and `list_for_signal` for the
history view; aggregate fields used by the opportunities query live in
opportunities.py — keeping the LATERAL subquery next to the rest of
that read path makes it easier to evolve as one unit.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.domain.models import DetectedSignal, SignalFeedback
from app.repositories.base import TenantAwareRepository


class SignalFeedbackRepository(TenantAwareRepository[SignalFeedback]):
    model = SignalFeedback

    def list_for_signal(
        self, signal_id: UUID, *, limit: int = 100
    ) -> list[SignalFeedback]:
        """Newest first. Cross-tenant access is impossible because the
        base query is tenant-scoped — even if a caller passes a
        signal_id from another tenant, the WHERE tenant_id constraint
        on the join makes the result set empty."""
        stmt = (
            self._base_query()
            .where(SignalFeedback.signal_id == signal_id)
            .order_by(SignalFeedback.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def signal_belongs_to_tenant(self, signal_id: UUID) -> bool:
        """Used by the service before insert to surface a 404 instead
        of letting the FK fail at flush time."""
        stmt = (
            select(DetectedSignal.id)
            .where(DetectedSignal.id == signal_id)
            .where(DetectedSignal.tenant_id == self.tenant_id)
            .limit(1)
        )
        return self.db.execute(stmt).first() is not None
