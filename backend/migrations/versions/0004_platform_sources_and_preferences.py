"""platform source pool + tenant signal preferences

Revision ID: 0004_platform_sources_and_preferences
Revises: 0003_tenant_trial
Create Date: 2026-05-01

Strategy
--------
Sources stop being tenant-owned and become a centrally-managed platform
pool tagged across four taxonomies (region / sector / customer-type /
signal-focus). Tenants pick preferences and the pipeline matches sources
to tenants by tag intersection.

Compatibility
-------------
* `sources.tenant_id` becomes NULLABLE. NULL = platform pool, any non-NULL
  value = legacy tenant-owned row preserved for FK / history integrity
  (pipeline_runs, raw_source_items, detected_signals still resolve their
  source_id). Legacy rows are filtered out of the new matching query
  (WHERE tenant_id IS NULL), so they never produce new pipeline work.
* The old `uq_sources_tenant_url` constraint is replaced with a partial
  unique index on `url WHERE tenant_id IS NULL` so two legacy tenants
  that subscribed to the same RSS keep their rows, and the platform pool
  still rejects duplicate URLs.
* `uq_raw_items_source_external (source_id, external_id)` is replaced
  with `(tenant_id, source_id, external_id)`. With shared platform
  sources, two tenants ingesting the same item from the same source must
  each get their own raw row. The repo layer was already filtering by
  tenant_id; this migration aligns the DB constraint with that.

Data preservation
-----------------
No row deletes. No UPDATEs to legacy data. Tag columns default to '{}'
so existing rows simply have empty tags and are excluded from the new
matching path until a platform admin re-creates them in the pool.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_platform_sources_and_preferences"
down_revision = "0003_tenant_trial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. sources: tenant_id becomes nullable, add taxonomy + metadata
    # ---------------------------------------------------------------
    op.alter_column("sources", "tenant_id", nullable=True)

    op.add_column(
        "sources",
        sa.Column(
            "region_tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "sector_tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "customer_type_tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "signal_focus_tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "sources",
        sa.Column("language", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column(
            "priority", sa.Integer(), nullable=False, server_default=sa.text("100")
        ),
    )
    op.add_column(
        "sources",
        sa.Column("quality_score", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("noise_level", sa.Numeric(precision=3, scale=2), nullable=True),
    )

    # GIN indexes on the four tag arrays — used by the && (overlap)
    # matching query in PlatformSourceRepository.match_for_preferences.
    op.create_index(
        "ix_sources_region_tags_gin",
        "sources",
        ["region_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_sources_sector_tags_gin",
        "sources",
        ["sector_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_sources_customer_type_tags_gin",
        "sources",
        ["customer_type_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_sources_signal_focus_tags_gin",
        "sources",
        ["signal_focus_tags"],
        postgresql_using="gin",
    )

    # URL uniqueness moves from (tenant_id, url) to a partial unique on
    # platform pool only. Legacy tenant rows can keep their pre-existing
    # url collisions across tenants.
    op.drop_constraint("uq_sources_tenant_url", "sources", type_="unique")
    op.create_index(
        "uq_sources_platform_url",
        "sources",
        ["url"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    # Partial active-platform index for the matching hot path.
    op.create_index(
        "ix_sources_platform_active",
        "sources",
        ["is_active"],
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    # ---------------------------------------------------------------
    # 2. raw_source_items: tenant-scope the (source_id, external_id)
    # uniqueness so two tenants can ingest the same item from a shared
    # platform source.
    # ---------------------------------------------------------------
    op.drop_constraint(
        "uq_raw_items_source_external", "raw_source_items", type_="unique"
    )
    op.create_unique_constraint(
        "uq_raw_items_tenant_source_external",
        "raw_source_items",
        ["tenant_id", "source_id", "external_id"],
    )

    # ---------------------------------------------------------------
    # 3. tenant_signal_preferences (one row per tenant, UPSERT semantics)
    # ---------------------------------------------------------------
    op.create_table(
        "tenant_signal_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_customer_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "sectors",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "regions",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "signal_focuses",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "minimum_confidence",
            sa.Numeric(precision=4, scale=3),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
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
        sa.UniqueConstraint("tenant_id", name="uq_tenant_signal_preferences_tenant"),
        sa.CheckConstraint(
            "minimum_confidence >= 0 AND minimum_confidence <= 1",
            name="ck_tenant_signal_preferences_confidence",
        ),
    )


def downgrade() -> None:
    op.drop_table("tenant_signal_preferences")

    op.drop_constraint(
        "uq_raw_items_tenant_source_external",
        "raw_source_items",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_raw_items_source_external",
        "raw_source_items",
        ["source_id", "external_id"],
    )

    op.drop_index("ix_sources_platform_active", table_name="sources")
    op.drop_index("uq_sources_platform_url", table_name="sources")
    op.create_unique_constraint(
        "uq_sources_tenant_url", "sources", ["tenant_id", "url"]
    )

    op.drop_index("ix_sources_signal_focus_tags_gin", table_name="sources")
    op.drop_index("ix_sources_customer_type_tags_gin", table_name="sources")
    op.drop_index("ix_sources_sector_tags_gin", table_name="sources")
    op.drop_index("ix_sources_region_tags_gin", table_name="sources")

    op.drop_column("sources", "noise_level")
    op.drop_column("sources", "quality_score")
    op.drop_column("sources", "priority")
    op.drop_column("sources", "language")
    op.drop_column("sources", "signal_focus_tags")
    op.drop_column("sources", "customer_type_tags")
    op.drop_column("sources", "sector_tags")
    op.drop_column("sources", "region_tags")

    # Downgrade requires no NULLs in tenant_id; if any platform-pool rows
    # exist they must be deleted or assigned a tenant before downgrading.
    op.execute("DELETE FROM sources WHERE tenant_id IS NULL")
    op.alter_column("sources", "tenant_id", nullable=False)
