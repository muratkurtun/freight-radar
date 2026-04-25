"""add trial / subscription columns to tenants

Revision ID: 0003_tenant_trial
Revises: 0002_user_full_name
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_tenant_trial"
down_revision = "0002_user_full_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "subscription_status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_tenants_subscription_status",
        "tenants",
        "subscription_status IN ('trial','active')",
    )
    # Existing tenants (seeded via scripts.seed_tenant before this migration)
    # are grandfathered as 'active' — they never had a trial and must not
    # suddenly be locked out.
    op.execute("UPDATE tenants SET subscription_status = 'active'")


def downgrade() -> None:
    op.drop_constraint("ck_tenants_subscription_status", "tenants", type_="check")
    op.drop_column("tenants", "trial_ends_at")
    op.drop_column("tenants", "trial_started_at")
    op.drop_column("tenants", "subscription_status")
