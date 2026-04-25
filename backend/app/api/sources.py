from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    db_session,
    require_active_subscription,
    require_tenant_admin,
    tenant_context,
)
from app.domain.schemas import (
    PagedSources,
    Page,
    SourceCreate,
    SourceRead,
    SourceUpdate,
)
from app.security.tenant_context import TenantContext
from app.services.source_service import SourceService

router = APIRouter(
    prefix="/sources",
    tags=["sources"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("", response_model=PagedSources)
def list_sources(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> PagedSources:
    items, total = SourceService(db, ctx).list(limit=limit, offset=offset)
    return PagedSources(
        items=[SourceRead.model_validate(s) for s in items],
        page=Page(limit=limit, offset=offset, total=total),
    )


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> SourceRead:
    source = SourceService(db, ctx).create(payload)
    return SourceRead.model_validate(source)


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: UUID,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> SourceRead:
    source = SourceService(db, ctx).get(source_id)
    return SourceRead.model_validate(source)


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> SourceRead:
    source = SourceService(db, ctx).update(source_id, payload)
    return SourceRead.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: UUID,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> None:
    SourceService(db, ctx).delete(source_id)
