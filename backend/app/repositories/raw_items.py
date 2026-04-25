"""Raw item repository.

Two dedupe keys, both enforced by UNIQUE constraints at the DB:
  - (source_id, external_id)  — same source emitted the same entry ID
  - (tenant_id, content_hash) — same text reached us via a different path

`insert_if_not_exists` checks both before inserting. The DB constraints
are the authoritative guard; the app-level check is a fast path that
avoids an IntegrityError + rollback on the common duplicate case."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.domain.models import RawSourceItem
from app.repositories.base import TenantAwareRepository


class RawItemRepository(TenantAwareRepository[RawSourceItem]):
    model = RawSourceItem

    def exists_for_source(self, source_id: UUID, external_id: str) -> bool:
        stmt = (
            select(RawSourceItem.id)
            .where(RawSourceItem.tenant_id == self.tenant_id)
            .where(RawSourceItem.source_id == source_id)
            .where(RawSourceItem.external_id == external_id)
            .limit(1)
        )
        return self.db.execute(stmt).first() is not None

    def find_by_content_hash(self, content_hash: str) -> RawSourceItem | None:
        stmt = self._base_query().where(RawSourceItem.content_hash == content_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def insert_if_not_exists(self, item: RawSourceItem) -> RawSourceItem | None:
        """Insert unless either dedupe key already matches an existing row.

        Returns the inserted row, or None when a duplicate was detected."""
        if self.exists_for_source(item.source_id, item.external_id):
            return None
        if self.find_by_content_hash(item.content_hash) is not None:
            return None
        return self.add(item)

    def list_unprocessed(self, *, limit: int = 50) -> list[RawSourceItem]:
        stmt = (
            self._base_query()
            .where(RawSourceItem.processed_at.is_(None))
            .order_by(RawSourceItem.fetched_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def mark_processed(self, item: RawSourceItem) -> None:
        item.processed_at = datetime.now(timezone.utc)
        self.db.flush()
