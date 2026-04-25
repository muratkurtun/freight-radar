from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.domain.models import Source
from app.domain.schemas import SourceCreate, SourceUpdate
from app.repositories.sources import SourceRepository
from app.security.tenant_context import TenantContext


class SourceService:
    def __init__(self, db: Session, ctx: TenantContext):
        self.db = db
        self.ctx = ctx
        self.repo = SourceRepository(db, ctx.tenant_id)

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Source], int]:
        items = self.repo.list(limit=limit, offset=offset)
        total = self.repo.count()
        return items, total

    def get(self, source_id: UUID) -> Source:
        return self.repo.get_or_404(source_id)

    def create(self, payload: SourceCreate) -> Source:
        if self.repo.find_by_url(payload.url) is not None:
            raise ConflictError("A source with this URL already exists for the tenant")
        source = Source(
            tenant_id=self.ctx.tenant_id,
            source_type=payload.source_type.value,
            name=payload.name,
            url=payload.url,
            config=payload.config,
            is_active=payload.is_active,
        )
        self.repo.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def update(self, source_id: UUID, payload: SourceUpdate) -> Source:
        source = self.repo.get_or_404(source_id)
        if payload.name is not None:
            source.name = payload.name
        if payload.url is not None and payload.url != source.url:
            if self.repo.find_by_url(payload.url) is not None:
                raise ConflictError("A source with this URL already exists for the tenant")
            source.url = payload.url
        if payload.config is not None:
            source.config = payload.config
        if payload.is_active is not None:
            source.is_active = payload.is_active
        self.db.commit()
        self.db.refresh(source)
        return source

    def delete(self, source_id: UUID) -> None:
        source = self.repo.get_or_404(source_id)
        self.repo.delete(source)
        self.db.commit()
