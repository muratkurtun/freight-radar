"""JWT access token service.

Symmetric HS256 by default. No refresh tokens — clients re-login when
the access token expires.

Claim contract
--------------
    sub                  user UUID (string)
    tenant_id            tenant UUID (string)   — REQUIRED
    email                user email
    full_name            display name (optional, may be null)
    role                 UserRole value
    subscription_status  'trial' | 'active' (snapshot at login time)
    trial_ends_at        ISO timestamp (null for active subscriptions)
    iat, exp             standard

subscription_status in the token is a UX hint only — every business
endpoint re-checks the live value in the DB via
`require_active_subscription`."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings
from app.core.errors import AuthError

_REQUIRED_CLAIMS: tuple[str, ...] = ("sub", "tenant_id", "email", "role")


def create_access_token(
    *,
    subject: str,
    tenant_id: str,
    email: str,
    role: str,
    subscription_status: str,
    trial_ends_at: datetime | None,
    full_name: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "email": email,
        "full_name": full_name,
        "role": role,
        "subscription_status": subscription_status,
        "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthError("Invalid or expired token") from exc

    for claim in _REQUIRED_CLAIMS:
        if not payload.get(claim):
            raise AuthError("Invalid or expired token")
    return payload
