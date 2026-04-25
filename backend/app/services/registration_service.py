"""Public self-serve registration → tenant + admin user + 7-day trial.

One transaction:
    1. validate email is globally unused
    2. derive a unique slug from tenant_name
    3. insert Tenant (subscription_status='trial', trial_ends_at = now + TRIAL_DAYS)
    4. insert User (tenant_admin role)
    5. mint a JWT and return it along with the CurrentUser snapshot

Everything rolls back on any error — no half-created tenant."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ConflictError
from app.domain.enums import SubscriptionStatus, UserRole
from app.domain.models import Tenant, User
from app.domain.schemas import CurrentUser, RegisterRequest, RegisterResponse
from app.repositories.tenants import TenantRepository
from app.repositories.users import UserRepository
from app.security.jwt import create_access_token
from app.security.passwords import hash_password

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower()).strip("-")
    return base[:80] or "tenant"


class RegistrationService:
    def __init__(self, db: Session):
        self.db = db
        self.tenants = TenantRepository(db)
        self.users = UserRepository(db)

    def register(self, payload: RegisterRequest) -> RegisterResponse:
        email = payload.email.lower()
        if self.users.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists")

        slug = self._unique_slug(payload.tenant_name)
        now = datetime.now(timezone.utc)
        trial_days = get_settings().trial_days
        trial_ends_at = now + timedelta(days=trial_days)

        tenant = Tenant(
            name=payload.tenant_name.strip(),
            slug=slug,
            is_active=True,
            subscription_status=SubscriptionStatus.TRIAL.value,
            trial_started_at=now,
            trial_ends_at=trial_ends_at,
        )
        self.tenants.add(tenant)

        user = User(
            tenant_id=tenant.id,
            email=email,
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=UserRole.TENANT_ADMIN.value,
            is_active=True,
        )
        self.users.add(user)

        self.db.commit()
        self.db.refresh(tenant)
        self.db.refresh(user)

        token = create_access_token(
            subject=str(user.id),
            tenant_id=str(tenant.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            subscription_status=tenant.subscription_status,
            trial_ends_at=tenant.trial_ends_at,
        )
        current = CurrentUser(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            full_name=user.full_name,
            role=UserRole(user.role),
            subscription_status=SubscriptionStatus(tenant.subscription_status),
            trial_ends_at=tenant.trial_ends_at,
        )
        return RegisterResponse(access_token=token, user=current)

    def _unique_slug(self, tenant_name: str) -> str:
        """Try the derived slug; if taken, append a random 6-char suffix.

        Keeps registration non-blocking — we don't ask the user to pick a
        slug. Race with another registration is handled by the UNIQUE
        constraint on tenants.slug: a 23505 would bubble up as a 500 to
        the client, extremely rare at MVP scale."""
        base = _slugify(tenant_name)
        if not self.tenants.slug_exists(base):
            return base
        for _ in range(5):
            candidate = f"{base}-{secrets.token_hex(3)}"
            if not self.tenants.slug_exists(candidate):
                return candidate
        raise ConflictError("Could not allocate a tenant slug, please retry")
