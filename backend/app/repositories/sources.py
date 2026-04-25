from sqlalchemy import select

from app.domain.models import Source
from app.repositories.base import TenantAwareRepository


class SourceRepository(TenantAwareRepository[Source]):
    model = Source

    def list_active(self) -> list[Source]:
        stmt = self._base_query().where(Source.is_active.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def find_by_url(self, url: str) -> Source | None:
        stmt = self._base_query().where(Source.url == url)
        return self.db.execute(stmt).scalar_one_or_none()

    def count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Source).where(Source.tenant_id == self.tenant_id)
        return int(self.db.execute(stmt).scalar_one())
