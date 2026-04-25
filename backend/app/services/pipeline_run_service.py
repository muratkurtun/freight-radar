"""Pipeline-run read service + manual trigger helper.

This lives next to the pipeline orchestration service but keeps a
narrow responsibility: expose recent runs to the UI and provide the
background helper used by the `/pipeline/run` endpoint."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.domain.enums import PipelineRunStatus
from app.domain.models import PipelineRun
from app.repositories.pipeline_runs import PipelineRunRepository
from app.security.tenant_context import TenantContext
from app.services.pipeline_service import run_pipeline_for_tenant

logger = get_logger(__name__)


class PipelineRunService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.repo = PipelineRunRepository(db, ctx.tenant_id)

    def list_recent(
        self,
        *,
        source_id: UUID | None = None,
        status: PipelineRunStatus | None = None,
        limit: int = 20,
    ) -> list[PipelineRun]:
        return self.repo.list_recent(source_id=source_id, status=status, limit=limit)


def run_tenant_pipeline_in_background(tenant_id: UUID) -> None:
    """Open a fresh session, run the tenant pipeline, close.

    Meant to be handed to FastAPI's BackgroundTasks. Never lets an
    exception escape — failures are logged; the pipeline_runs table is
    the authoritative audit trail."""
    with SessionLocal() as db:
        try:
            run_pipeline_for_tenant(db, tenant_id)
        except Exception:
            logger.exception("Manual pipeline trigger failed tenant=%s", tenant_id)
