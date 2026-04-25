"""Tenant repository — cross-tenant access.

Does NOT extend TenantAwareRepository because its reads/writes span
tenants by design. Only platform_admin-level operations should reach
this repo; regular app code should never need it."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Tenant


class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, tenant_id: UUID) -> Tenant | None:
        return self.db.get(Tenant, tenant_id)

    def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def slug_exists(self, slug: str) -> bool:
        return self.get_by_slug(slug) is not None

    def list_active(self) -> list[Tenant]:
        stmt = select(Tenant).where(Tenant.is_active.is_(True)).order_by(Tenant.name)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        self.db.flush()
        return tenant
