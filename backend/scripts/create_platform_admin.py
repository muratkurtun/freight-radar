"""Bootstrap a platform_admin user.

This is the *only* sanctioned way to create a PLATFORM_ADMIN. The
public /auth/register endpoint hardcodes the new user's role to
tenant_admin and the RegisterRequest schema has no `role` field
(audited Phase 11), so a hostile client cannot mint a platform admin
through the HTTP surface — all platform-admin creation goes through
this script, which is run by the platform owner with shell access.

Usage (inside the backend container, with PYTHONPATH=/app):

    cd /app
    python scripts/create_platform_admin.py \\
        --email admin@example.com \\
        --password '...' \\
        --full-name 'Platform Admin'

A "platform tenant" is required because `app_users.tenant_id` is
NOT NULL. By default the script gets-or-creates a tenant with slug
`platform`; pass --tenant-slug / --tenant-name to override.

Re-running is safe in two modes:
  - default              : duplicate email → exits with rc=2
  - --update-existing    : promotes the existing row to PLATFORM_ADMIN,
                           resets the password, and ensures is_active.
                           The user's tenant_id stays as-is — moving a
                           user across tenants is destructive (drops
                           their existing data scope) so the script
                           refuses unless the target tenant matches.
"""
from __future__ import annotations

import argparse
import sys
from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.enums import SubscriptionStatus, UserRole
from app.domain.models import Tenant, User
from app.repositories.tenants import TenantRepository
from app.repositories.users import UserRepository
from app.security.passwords import hash_password


def _get_or_create_platform_tenant(
    tenants: TenantRepository, *, name: str, slug: str
) -> tuple[Tenant, str]:
    """Return (tenant, action) where action ∈ {'created','existing'}."""
    existing = tenants.get_by_slug(slug)
    if existing is not None:
        return existing, "existing"
    tenant = Tenant(
        name=name,
        slug=slug,
        is_active=True,
        # Platform tenant exists indefinitely — no trial, no expiry.
        # platform_admin's effective subscription_status is the tenant's,
        # so 'active' here means the platform admin is never blocked by
        # require_active_subscription.
        subscription_status=SubscriptionStatus.ACTIVE.value,
    )
    tenants.add(tenant)
    return tenant, "created"


def run(
    *,
    email: str,
    password: str,
    full_name: str,
    tenant_name: str,
    tenant_slug: str,
    update_existing: bool,
    session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    stderr=sys.stderr,
    stdout=sys.stdout,
) -> int:
    """Library-level entry point. Returns the script exit code so tests
    can drive it without spawning a subprocess."""
    email_norm = email.strip().lower()
    if not email_norm or "@" not in email_norm:
        print("invalid email", file=stderr)
        return 2
    if not password or len(password) < 8:
        # Password content NEVER printed; only the length-policy reason.
        print("password must be at least 8 characters", file=stderr)
        return 2
    if not full_name.strip():
        print("full-name is required", file=stderr)
        return 2

    with session_factory() as db:
        users = UserRepository(db)
        tenants = TenantRepository(db)

        tenant, tenant_action = _get_or_create_platform_tenant(
            tenants, name=tenant_name, slug=tenant_slug
        )

        existing = users.get_by_email(email_norm)

        if existing is not None and not update_existing:
            print(
                f"user already exists with email={email_norm}; "
                "pass --update-existing to promote + reset password",
                file=stderr,
            )
            return 2

        if existing is not None:
            # --update-existing path: refuse to silently move the user
            # across tenants. A platform admin can live in any tenant
            # (their role bypasses tenant scope), but moving them
            # changes which tenant's data they default to seeing on
            # login. Force the operator to be explicit.
            if existing.tenant_id != tenant.id:
                print(
                    "refusing to update: existing user lives in a different "
                    f"tenant ({existing.tenant_id}); pass matching "
                    "--tenant-slug or remove the user first",
                    file=stderr,
                )
                return 2
            existing.role = UserRole.PLATFORM_ADMIN.value
            existing.password_hash = hash_password(password)
            existing.is_active = True
            existing.full_name = full_name.strip()
            db.commit()
            print(
                f"updated user email={email_norm} role={existing.role} "
                f"tenant={tenant.slug} action=updated",
                file=stdout,
            )
            return 0

        user = User(
            tenant_id=tenant.id,
            email=email_norm,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=UserRole.PLATFORM_ADMIN.value,
            is_active=True,
        )
        users.add(user)
        db.commit()

        print(
            f"created user email={email_norm} role={user.role} "
            f"tenant={tenant.slug} (tenant_action={tenant_action})",
            file=stdout,
        )
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap a platform_admin user.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        required=True,
        help="Plain password (NEVER logged); will be passlib-bcrypt hashed.",
    )
    parser.add_argument("--full-name", required=True)
    parser.add_argument(
        "--tenant-name",
        default="Opportunity Radar Platform",
        help="Display name for the platform tenant. Used only when the "
        "tenant does not already exist.",
    )
    parser.add_argument(
        "--tenant-slug",
        default="platform",
        help="Slug for the platform tenant. Get-or-create on this key.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Promote an existing user (by email) to PLATFORM_ADMIN and "
        "reset their password. Refuses to move the user across tenants.",
    )
    args = parser.parse_args()

    rc = run(
        email=args.email,
        password=args.password,
        full_name=args.full_name,
        tenant_name=args.tenant_name,
        tenant_slug=args.tenant_slug,
        update_existing=args.update_existing,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
