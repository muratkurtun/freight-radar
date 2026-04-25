"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- tenants ----
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ---- app_users ----
    op.create_table(
        "app_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "email", name="uq_app_users_tenant_email"),
        sa.CheckConstraint(
            "role IN ('platform_admin','tenant_admin','tenant_user')",
            name="ck_app_users_role",
        ),
    )
    op.create_index("ix_app_users_tenant", "app_users", ["tenant_id"])

    # ---- sources ----
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "url", name="uq_sources_tenant_url"),
        sa.CheckConstraint(
            "source_type IN ('news','job_board','company_website')",
            name="ck_sources_source_type",
        ),
    )
    op.create_index("ix_sources_tenant_active", "sources", ["tenant_id", "is_active"])

    # ---- pipeline_runs ----
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_collected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','success','failed')",
            name="ck_pipeline_runs_status",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_pipeline_runs_finish",
        ),
    )
    op.create_index(
        "ix_pipeline_runs_tenant_started",
        "pipeline_runs",
        ["tenant_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_pipeline_runs_source_started",
        "pipeline_runs",
        ["source_id", sa.text("started_at DESC")],
    )

    # ---- raw_source_items ----
    op.create_table(
        "raw_source_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pipeline_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_id", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "external_id", name="uq_raw_items_source_external"),
        sa.UniqueConstraint("tenant_id", "content_hash", name="uq_raw_items_tenant_content"),
    )
    op.create_index(
        "ix_raw_items_tenant_processed", "raw_source_items", ["tenant_id", "processed_at"]
    )
    op.create_index("ix_raw_items_source", "raw_source_items", ["source_id"])
    op.create_index("ix_raw_items_run", "raw_source_items", ["pipeline_run_id"])

    # ---- detected_signals ----
    op.create_table(
        "detected_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_source_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_source_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_type", sa.String(length=40), nullable=False),
        sa.Column(
            "confidence", sa.Numeric(precision=4, scale=3), nullable=False, server_default="0"
        ),
        sa.Column("signal_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("role_title", sa.String(length=255), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "signal_hash", name="uq_signals_tenant_hash"),
        sa.CheckConstraint(
            "signal_type IN ('warehouse_opening','supplier_change','hiring_supply_chain_role')",
            name="ck_signals_signal_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending_review','approved','rejected')",
            name="ck_signals_review_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_signals_confidence_range",
        ),
    )
    op.create_index("ix_signals_tenant_status", "detected_signals", ["tenant_id", "review_status"])
    op.create_index("ix_signals_tenant_type", "detected_signals", ["tenant_id", "signal_type"])
    op.create_index(
        "ix_signals_tenant_created",
        "detected_signals",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_signals_raw_item", "detected_signals", ["raw_source_item_id"])

    # ---- signal_reviews ----
    op.create_table(
        "signal_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "detected_signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("detected_signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "action IN ('approve','reject')",
            name="ck_signal_reviews_action",
        ),
        sa.CheckConstraint(
            "action <> 'reject' OR reason IS NOT NULL",
            name="ck_signal_reviews_reject_reason",
        ),
    )
    op.create_index("ix_signal_reviews_signal", "signal_reviews", ["detected_signal_id"])
    op.create_index(
        "ix_signal_reviews_tenant_created",
        "signal_reviews",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_signal_reviews_user", "signal_reviews", ["reviewer_user_id"])


def downgrade() -> None:
    op.drop_table("signal_reviews")
    op.drop_table("detected_signals")
    op.drop_table("raw_source_items")
    op.drop_table("pipeline_runs")
    op.drop_table("sources")
    op.drop_table("app_users")
    op.drop_table("tenants")
