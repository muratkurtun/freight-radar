"""Repository for tenant-scoped Company entities.

The hot path here is `get_or_create_by_normalized_name`, called from
PipelineService for every signal that names a company. The
(tenant_id, normalized_name) UNIQUE constraint on the table is the
authoritative dedupe; this repo's job is to keep the in-Python flow
idempotent and avoid an IntegrityError on the common case.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.normalization import normalize_company_name
from app.domain.models import Company
from app.repositories.base import TenantAwareRepository


class CompanyRepository(TenantAwareRepository[Company]):
    model = Company

    def find_by_normalized_name(self, normalized: str) -> Company | None:
        if not normalized:
            return None
        stmt = self._base_query().where(Company.normalized_name == normalized)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create_by_normalized_name(
        self,
        *,
        raw_name: str,
        sector: str | None = None,
        region: str | None = None,
    ) -> Company | None:
        """Return the matching Company for this tenant, creating one if
        none exists. Returns None when the input normalizes to empty —
        callers must treat that as "skip company linkage" (we never
        create a row for a missing / unparseable name).

        On match, sector/region are filled IN PLACE only when the
        existing column is NULL — first-set wins, so a noisy second
        signal does not overwrite a curated value, but a company
        created from an early signal that lacked sector still gets
        backfilled the next time we see one.
        """
        normalized = normalize_company_name(raw_name)
        if not normalized:
            return None

        existing = self.find_by_normalized_name(normalized)
        if existing is not None:
            updated = False
            if existing.sector is None and sector:
                existing.sector = sector
                updated = True
            if existing.region is None and region:
                existing.region = region
                updated = True
            if updated:
                existing.updated_at = datetime.now(timezone.utc)
                self.db.flush()
            return existing

        company = Company(
            tenant_id=self.tenant_id,
            name=raw_name.strip(),
            normalized_name=normalized,
            sector=sector,
            region=region,
        )
        return self.add(company)
