from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AuthError, PermissionError, SubscriptionExpiredError
from app.db.session import get_db
from app.domain.enums import SubscriptionStatus, UserRole
from app.domain.schemas import CurrentUser
from app.repositories.tenants import TenantRepository
from app.repositories.users import UserRepository
from app.security.jwt import decode_token
from app.security.tenant_context import TenantContext


def db_session() -> Iterator[Session]:
    yield from get_db()


def tenant_context(authorization: str | None = Header(default=None)) -> TenantContext:
    """Decode the bearer token into a TenantContext.

    Stays lean: only JWT-derived identity. Subscription status is NOT
    checked here so that /auth/me and similar endpoints keep working
    for users whose trial has ended."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    try:
        return TenantContext(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=payload["role"],
            email=payload.get("email"),
            full_name=payload.get("full_name"),
        )
    except (KeyError, ValueError) as exc:
        raise AuthError("Invalid token payload") from exc


def _effective_status(tenant_status: str, trial_ends_at: datetime | None) -> SubscriptionStatus:
    if tenant_status == SubscriptionStatus.ACTIVE.value:
        return SubscriptionStatus.ACTIVE
    if tenant_status == SubscriptionStatus.TRIAL.value:
        if trial_ends_at is None or trial_ends_at > datetime.now(timezone.utc):
            return SubscriptionStatus.TRIAL
        return SubscriptionStatus.EXPIRED
    return SubscriptionStatus.EXPIRED


def get_current_user(
    ctx: TenantContext = Depends(tenant_context),
    db: Session = Depends(db_session),
) -> CurrentUser:
    """Resolve the current user + tenant from the DB.

    Does the DB hit on purpose: a token that outlived a deactivation or
    a trial expiration must stop working immediately. The returned
    `subscription_status` is the *effective* value (derives EXPIRED
    from trial_ends_at) so the frontend has a single source of truth."""
    user = UserRepository(db).get(ctx.user_id)
    if user is None or not user.is_active or user.tenant_id != ctx.tenant_id:
        raise AuthError("User is not authorized")
    tenant = TenantRepository(db).get(user.tenant_id)
    if tenant is None or not tenant.is_active:
        raise AuthError("User is not authorized")

    return CurrentUser(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        role=UserRole(user.role),
        subscription_status=_effective_status(
            tenant.subscription_status, tenant.trial_ends_at
        ),
        trial_ends_at=tenant.trial_ends_at,
    )


def require_tenant_admin(ctx: TenantContext = Depends(tenant_context)) -> TenantContext:
    if ctx.role not in {"tenant_admin", "platform_admin"}:
        raise PermissionError("Tenant admin role required")
    return ctx


def require_platform_admin(ctx: TenantContext = Depends(tenant_context)) -> TenantContext:
    """Strictly platform_admin. Tenant admins are NOT allowed — platform
    source pool management is cross-tenant and must not be reachable
    from a tenant admin role."""
    if ctx.role != UserRole.PLATFORM_ADMIN.value:
        raise PermissionError("Platform admin role required")
    return ctx


def require_active_subscription(
    ctx: TenantContext = Depends(tenant_context),
    db: Session = Depends(db_session),
) -> TenantContext:
    """Block the request when the tenant's trial has ended and no paid
    subscription is active.

    Applied as a router-level dependency on every business endpoint.
    NOT applied on /auth/* — expired users must still be able to log in
    and see their own status so the frontend can render the upgrade
    screen."""
    tenant = TenantRepository(db).get(ctx.tenant_id)
    if tenant is None or not tenant.is_active:
        raise AuthError("Tenant not available")

    status = _effective_status(tenant.subscription_status, tenant.trial_ends_at)
    if status == SubscriptionStatus.EXPIRED:
        raise SubscriptionExpiredError("Your trial has ended")
    return ctx
