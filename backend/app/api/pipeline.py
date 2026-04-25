"""Pipeline control & history endpoints (admin-only).

    POST /pipeline/run     -> fire the pipeline for the caller's tenant
                              as a background task; returns 202
    GET  /pipeline-runs    -> recent PipelineRun rows for the tenant

The trigger deliberately does not block the HTTP request. A manual
run can take minutes; the frontend polls `/pipeline-runs` to watch
progress. pipeline_runs is the authoritative status — the 202 response
is only an acknowledgement that the work was scheduled."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_active_subscription, require_tenant_admin
from app.domain.enums import PipelineRunStatus
from app.domain.schemas import (
    PagedPipelineRuns,
    PipelineRunRead,
    PipelineTriggerResponse,
)
from app.security.tenant_context import TenantContext
from app.services.pipeline_run_service import (
    PipelineRunService,
    run_tenant_pipeline_in_background,
)

trigger_router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_active_subscription)],
)
runs_router = APIRouter(
    prefix="/pipeline-runs",
    tags=["pipeline"],
    dependencies=[Depends(require_active_subscription)],
)


@trigger_router.post(
    "/run",
    response_model=PipelineTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_pipeline(
    background: BackgroundTasks,
    ctx: TenantContext = Depends(require_tenant_admin),
) -> PipelineTriggerResponse:
    background.add_task(run_tenant_pipeline_in_background, ctx.tenant_id)
    return PipelineTriggerResponse(
        tenant_id=ctx.tenant_id,
        message="Pipeline run scheduled",
    )


@runs_router.get("", response_model=PagedPipelineRuns)
def list_pipeline_runs(
    source_id: UUID | None = Query(default=None),
    run_status: PipelineRunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> PagedPipelineRuns:
    rows = PipelineRunService(db, ctx).list_recent(
        source_id=source_id,
        status=run_status,
        limit=limit,
    )
    return PagedPipelineRuns(items=[PipelineRunRead.model_validate(r) for r in rows])
