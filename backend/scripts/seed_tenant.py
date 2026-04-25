"""Seed a default tenant + admin user.

Usage:
    python -m scripts.seed_tenant \\
        --tenant-name "Acme" --tenant-slug acme \\
        --admin-email admin@acme.com --admin-password changeme \\
        [--admin-full-name "Jane Admin"]
"""
import argparse

from app.db.session import SessionLocal
from app.domain.enums import SubscriptionStatus, UserRole
from app.domain.models import Tenant, User
from app.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--admin-full-name", default=None)
    args = parser.parse_args()

    with SessionLocal() as db:
        tenant = Tenant(
            name=args.tenant_name,
            slug=args.tenant_slug.lower(),
            subscription_status=SubscriptionStatus.ACTIVE.value,
        )
        db.add(tenant)
        db.flush()

        user = User(
            tenant_id=tenant.id,
            email=args.admin_email.lower(),
            full_name=args.admin_full_name,
            password_hash=hash_password(args.admin_password),
            role=UserRole.TENANT_ADMIN.value,
        )
        db.add(user)
        db.commit()

        print(f"Created tenant {tenant.slug} ({tenant.id})")
        print(f"Created admin user {user.email} ({user.id})")


if __name__ == "__main__":
    main()
