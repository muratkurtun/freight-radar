"""Tenant signal preferences endpoints.

Read: any authenticated tenant user (so the UI can display the current
profile without elevating the role).
Write: tenant_admin or platform_admin (require_tenant_admin already
covers both).

Subscription gate is applied at the router level: an expired tenant
cannot edit preferences until they upgrade."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import (
    db_session,
    require_active_subscription,
    require_tenant_admin,
    tenant_context,
)
from app.core.errors import NotFoundError
from app.domain.schemas import TenantPreferencesRead, TenantPreferencesUpsert
from app.security.tenant_context import TenantContext
from app.services.tenant_preference_service import TenantPreferenceService

router = APIRouter(
    prefix="/tenant/preferences",
    tags=["tenant-preferences"],
    dependencies=[Depends(require_active_subscription)],
)


@router.get("", response_model=TenantPreferencesRead)
def get_tenant_preferences(
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(tenant_context),
) -> TenantPreferencesRead:
    pref = TenantPreferenceService(db, ctx).get()
    if pref is None:
        raise NotFoundError("Tenant preferences not configured yet")
    return TenantPreferencesRead.model_validate(pref)


@router.put(
    "",
    response_model=TenantPreferencesRead,
    status_code=status.HTTP_200_OK,
)
def upsert_tenant_preferences(
    payload: TenantPreferencesUpsert,
    db: Session = Depends(db_session),
    ctx: TenantContext = Depends(require_tenant_admin),
) -> TenantPreferencesRead:
    pref = TenantPreferenceService(db, ctx).upsert(payload)
    return TenantPreferencesRead.model_validate(pref)
