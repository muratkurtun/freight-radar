"""Repository for tenant_signal_preferences.

One row per tenant. The service layer enforces UPSERT semantics; this
repo provides the get/insert/update primitives. Scoped via a tenant_id
in the constructor like the other tenant-aware repos."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import TenantSignalPreference


class TenantPreferenceRepository:
    def __init__(self, db: Session, tenant_id):
        self.db = db
        self.tenant_id = tenant_id

    def get(self) -> TenantSignalPreference | None:
        stmt = select(TenantSignalPreference).where(
            TenantSignalPreference.tenant_id == self.tenant_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def add(self, pref: TenantSignalPreference) -> TenantSignalPreference:
        if pref.tenant_id != self.tenant_id:
            raise ValueError("Preference tenant_id does not match repository scope")
        self.db.add(pref)
        self.db.flush()
        return pref
