"""Platform source pool admin endpoints.

Strictly platform_admin role. Tenant admins (even within an active
subscription) cannot reach these — `require_platform_admin` rejects
everything but `platform_admin`."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_platform_admin
from app.domain.schemas import (
    Page,
    PagedPlatformSources,
    PlatformSourceCreate,
    PlatformSourceRead,
    PlatformSourceUpdate,
)
from app.security.tenant_context import TenantContext
from app.services.platform_source_service import PlatformSourceService

router = APIRouter(
    prefix="/platform/sources",
    tags=["platform-sources"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("", response_model=PagedPlatformSources)
def list_platform_sources(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(db_session),
    _ctx: TenantContext = Depends(require_platform_admin),
) -> PagedPlatformSources:
    items, total = PlatformSourceService(db).list(limit=limit, offset=offset)
    return PagedPlatformSources(
        items=[PlatformSourceRead.model_validate(s) for s in items],
        page=Page(limit=limit, offset=offset, total=total),
    )


@router.post("", response_model=PlatformSourceRead, status_code=status.HTTP_201_CREATED)
def create_platform_source(
    payload: PlatformSourceCreate,
    db: Session = Depends(db_session),
    _ctx: TenantContext = Depends(require_platform_admin),
) -> PlatformSourceRead:
    source = PlatformSourceService(db).create(payload)
    return PlatformSourceRead.model_validate(source)


@router.get("/{source_id}", response_model=PlatformSourceRead)
def get_platform_source(
    source_id: UUID,
    db: Session = Depends(db_session),
    _ctx: TenantContext = Depends(require_platform_admin),
) -> PlatformSourceRead:
    source = PlatformSourceService(db).get(source_id)
    return PlatformSourceRead.model_validate(source)


@router.patch("/{source_id}", response_model=PlatformSourceRead)
def update_platform_source(
    source_id: UUID,
    payload: PlatformSourceUpdate,
    db: Session = Depends(db_session),
    _ctx: TenantContext = Depends(require_platform_admin),
) -> PlatformSourceRead:
    source = PlatformSourceService(db).update(source_id, payload)
    return PlatformSourceRead.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_platform_source(
    source_id: UUID,
    db: Session = Depends(db_session),
    _ctx: TenantContext = Depends(require_platform_admin),
) -> None:
    PlatformSourceService(db).delete(source_id)
