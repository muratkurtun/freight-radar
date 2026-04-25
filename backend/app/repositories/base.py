from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, TenantMismatchError
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantAwareRepository(Generic[ModelT]):
    """Base repository that scopes every query to a tenant_id.

    Concrete repos pass the SQLAlchemy model class. All reads/writes go
    through helpers here so that tenant isolation is enforced in one place.
    """

    model: type[ModelT]

    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def _base_query(self):
        return select(self.model).where(self.model.tenant_id == self.tenant_id)  # type: ignore[attr-defined]

    def get(self, entity_id: UUID) -> ModelT | None:
        stmt = self._base_query().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_404(self, entity_id: UUID) -> ModelT:
        instance = self.get(entity_id)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} {entity_id} not found")
        return instance

    def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        stmt = self._base_query().limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, instance: ModelT) -> ModelT:
        if getattr(instance, "tenant_id", None) != self.tenant_id:
            raise TenantMismatchError("Instance tenant_id does not match repository scope")
        self.db.add(instance)
        self.db.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        if getattr(instance, "tenant_id", None) != self.tenant_id:
            raise TenantMismatchError("Instance tenant_id does not match repository scope")
        self.db.delete(instance)
        self.db.flush()
