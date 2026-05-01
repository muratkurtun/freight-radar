"""Service layer for the platform source pool. Platform-admin scope.

The CRUD here writes only platform-pool rows (`tenant_id IS NULL`). It
deliberately has no path to read or modify legacy tenant-owned source
rows — those are immutable history (see migration 0004)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.domain.models import Source
from app.domain.schemas import PlatformSourceCreate, PlatformSourceUpdate
from app.repositories.platform_sources import PlatformSourceRepository


class PlatformSourceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PlatformSourceRepository(db)

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Source], int]:
        items = self.repo.list(limit=limit, offset=offset)
        total = self.repo.count()
        return items, total

    def get(self, source_id: UUID) -> Source:
        return self.repo.get_or_404(source_id)

    def create(self, payload: PlatformSourceCreate) -> Source:
        if self.repo.find_by_url(payload.url) is not None:
            raise ConflictError("A platform source with this URL already exists")
        source = Source(
            tenant_id=None,
            source_type=payload.source_type.value,
            name=payload.name,
            url=payload.url,
            config=payload.config,
            is_active=payload.is_active,
            region_tags=list(payload.region_tags),
            sector_tags=list(payload.sector_tags),
            customer_type_tags=list(payload.customer_type_tags),
            signal_focus_tags=list(payload.signal_focus_tags),
            language=payload.language,
            priority=payload.priority,
            quality_score=payload.quality_score,
            noise_level=payload.noise_level,
        )
        self.repo.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def update(self, source_id: UUID, payload: PlatformSourceUpdate) -> Source:
        source = self.repo.get_or_404(source_id)
        if payload.name is not None:
            source.name = payload.name
        if payload.url is not None and payload.url != source.url:
            existing = self.repo.find_by_url(payload.url)
            if existing is not None and existing.id != source.id:
                raise ConflictError(
                    "A platform source with this URL already exists"
                )
            source.url = payload.url
        if payload.config is not None:
            source.config = payload.config
        if payload.is_active is not None:
            source.is_active = payload.is_active
        if payload.region_tags is not None:
            source.region_tags = list(payload.region_tags)
        if payload.sector_tags is not None:
            source.sector_tags = list(payload.sector_tags)
        if payload.customer_type_tags is not None:
            source.customer_type_tags = list(payload.customer_type_tags)
        if payload.signal_focus_tags is not None:
            source.signal_focus_tags = list(payload.signal_focus_tags)
        if payload.language is not None:
            source.language = payload.language
        if payload.priority is not None:
            source.priority = payload.priority
        if payload.quality_score is not None:
            source.quality_score = payload.quality_score
        if payload.noise_level is not None:
            source.noise_level = payload.noise_level
        self.db.commit()
        self.db.refresh(source)
        return source

    def delete(self, source_id: UUID) -> None:
        """Hard delete. Will cascade to pipeline_runs and raw_source_items
        for the same source via the existing FK ondelete=CASCADE. If the
        source has historical signals you want to keep, deactivate
        instead by patching is_active=false."""
        source = self.repo.get_or_404(source_id)
        self.repo.delete(source)
        self.db.commit()
