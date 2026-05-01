"""Repository for the platform source pool.

Unlike most repositories in this project, PlatformSourceRepository is
NOT tenant-scoped — sources live above tenants. The `tenant_id IS NULL`
predicate is the cross-cutting filter that excludes legacy pre-0004
tenant-owned rows from every query here. Legacy rows are kept in the
table only for FK / pipeline run history integrity; they must never
appear in admin lists or matching results.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.models import Source, TenantSignalPreference


def matches_preferences(source: Source, prefs: TenantSignalPreference) -> bool:
    """Pure-Python predicate that mirrors the SQL in
    `PlatformSourceRepository.match_for_preferences`.

    Rules:
      - inactive preference  → never matches
      - inactive source      → never matches
      - legacy tenant source (tenant_id IS NOT NULL) → never matches
      - all four tag dimensions must overlap (no wildcards):
          source.region_tags        ∩ prefs.regions               ≠ ∅
          source.sector_tags        ∩ prefs.sectors               ≠ ∅
          source.customer_type_tags ∩ prefs.target_customer_types ≠ ∅
          source.signal_focus_tags  ∩ prefs.signal_focuses        ≠ ∅

    The SQL version uses GIN-indexed Postgres array overlap (`&&`) for
    speed; this helper is the canonical spec the SQL must agree with."""
    if not prefs.is_active:
        return False
    if not source.is_active:
        return False
    if source.tenant_id is not None:
        return False
    return (
        bool(set(source.region_tags) & set(prefs.regions))
        and bool(set(source.sector_tags) & set(prefs.sectors))
        and bool(set(source.customer_type_tags) & set(prefs.target_customer_types))
        and bool(set(source.signal_focus_tags) & set(prefs.signal_focuses))
    )


class PlatformSourceRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- read --------------------------------------------------------

    def _platform_query(self):
        return select(Source).where(Source.tenant_id.is_(None))

    def get(self, source_id: UUID) -> Source | None:
        stmt = self._platform_query().where(Source.id == source_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_404(self, source_id: UUID) -> Source:
        source = self.get(source_id)
        if source is None:
            raise NotFoundError(f"Source {source_id} not found")
        return source

    def find_by_url(self, url: str) -> Source | None:
        stmt = self._platform_query().where(Source.url == url)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int = 50, offset: int = 0) -> list[Source]:
        stmt = (
            self._platform_query()
            .order_by(Source.priority.asc(), Source.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Source)
            .where(Source.tenant_id.is_(None))
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---- write -------------------------------------------------------

    def add(self, source: Source) -> Source:
        # Defensive: a platform pool row must not carry a tenant_id.
        if source.tenant_id is not None:
            raise ValueError("Platform source must have tenant_id=None")
        self.db.add(source)
        self.db.flush()
        return source

    def delete(self, source: Source) -> None:
        self.db.delete(source)
        self.db.flush()

    # ---- matching ----------------------------------------------------

    def match_for_preferences(
        self, prefs: TenantSignalPreference
    ) -> list[Source]:
        """Return active platform sources whose tag arrays overlap the
        tenant's preferences across all four taxonomies.

        Empty source-tag arrays match nothing (Postgres `&&` over an
        empty array is FALSE) — this is the deliberate "no wildcards"
        rule. An inactive preference returns no rows.

        Ordering is deterministic: priority asc, id asc."""
        if not prefs.is_active:
            return []
        stmt = (
            select(Source)
            .where(Source.tenant_id.is_(None))
            .where(Source.is_active.is_(True))
            .where(Source.region_tags.overlap(prefs.regions))
            .where(Source.sector_tags.overlap(prefs.sectors))
            .where(Source.customer_type_tags.overlap(prefs.target_customer_types))
            .where(Source.signal_focus_tags.overlap(prefs.signal_focuses))
            .order_by(Source.priority.asc(), Source.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
