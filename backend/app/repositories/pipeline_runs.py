"""Pipeline run repository — pipeline_runs table.

One row per source per scheduled run. `mark_finished` is the single
write path for closing out a run; the `status` + `finished_at` fields
can never drift because the caller always goes through this method.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.domain.enums import PipelineRunStatus
from app.domain.models import PipelineRun
from app.repositories.base import TenantAwareRepository


class PipelineRunRepository(TenantAwareRepository[PipelineRun]):
    model = PipelineRun

    def list_recent(
        self,
        *,
        source_id: UUID | None = None,
        status: PipelineRunStatus | None = None,
        limit: int = 20,
    ) -> list[PipelineRun]:
        stmt = self._base_query()
        if source_id is not None:
            stmt = stmt.where(PipelineRun.source_id == source_id)
        if status is not None:
            stmt = stmt.where(PipelineRun.status == status.value)
        stmt = stmt.order_by(PipelineRun.started_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def mark_finished(
        self,
        run: PipelineRun,
        *,
        status: PipelineRunStatus,
        items_collected: int,
        items_new: int,
        signals_detected: int,
        error_message: str | None = None,
    ) -> None:
        run.status = status.value
        run.finished_at = datetime.now(timezone.utc)
        run.items_collected = items_collected
        run.items_new = items_new
        run.signals_detected = signals_detected
        run.error_message = error_message
        self.db.flush()
