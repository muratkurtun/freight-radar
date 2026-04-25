"""add full_name to app_users

Revision ID: 0002_user_full_name
Revises: 0001_initial
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_user_full_name"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_users",
        sa.Column("full_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_users", "full_name")
