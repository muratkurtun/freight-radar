"""Service for tenant_signal_preferences. Single row per tenant; PUT
semantics (UPSERT) on the API."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.models import TenantSignalPreference
from app.domain.schemas import TenantPreferencesUpsert
from app.repositories.tenant_preferences import TenantPreferenceRepository
from app.security.tenant_context import TenantContext


class TenantPreferenceService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.repo = TenantPreferenceRepository(db, ctx.tenant_id)

    def get(self) -> TenantSignalPreference | None:
        return self.repo.get()

    def upsert(self, payload: TenantPreferencesUpsert) -> TenantSignalPreference:
        pref = self.repo.get()
        if pref is None:
            pref = TenantSignalPreference(
                tenant_id=self.ctx.tenant_id,
                target_customer_types=list(payload.target_customer_types),
                sectors=list(payload.sectors),
                regions=list(payload.regions),
                signal_focuses=list(payload.signal_focuses),
                minimum_confidence=payload.minimum_confidence,
                is_active=payload.is_active,
            )
            self.repo.add(pref)
        else:
            pref.target_customer_types = list(payload.target_customer_types)
            pref.sectors = list(payload.sectors)
            pref.regions = list(payload.regions)
            pref.signal_focuses = list(payload.signal_focuses)
            pref.minimum_confidence = payload.minimum_confidence
            pref.is_active = payload.is_active
            pref.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(pref)
        return pref
