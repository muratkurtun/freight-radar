"""User repository.

Login happens before a tenant is pinned, so lookups by email cross
tenants. Once authenticated, the JWT carries tenant_id and downstream
repos enforce tenant scope."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_tenant_and_email(self, tenant_id: UUID, email: str) -> User | None:
        stmt = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .where(User.email == email.lower())
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_tenant(self, tenant_id: UUID) -> list[User]:
        stmt = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(timezone.utc)
        self.db.flush()
