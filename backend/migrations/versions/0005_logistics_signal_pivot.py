"""logistics sales lead detection pivot

Revision ID: 0005_logistics_signal_pivot
Revises: 0004_platform_sources_and_preferences
Create Date: 2026-05-01

What this changes
-----------------
DetectedSignal becomes a logistics sales lead, not a generic supply-chain
event. The DB layer:

1. Drops `ck_signals_signal_type` so the application can introduce
   thirteen new signal_type values without locking out older rows that
   carry the legacy three (`warehouse_opening`, `supplier_change`,
   `hiring_supply_chain_role`). Validation lives in the app layer (the
   SignalType enum + LlmVerifier post-processing) from this revision on.

2. Adds eleven nullable columns capturing what a freight forwarder
   actually needs to act on a lead:
     target_customer_type, sector, region,
     detected_event, why_relevant_for_logistics, potential_logistics_need,
     recommended_services (text[]), urgency,
     suggested_sales_action, suggested_outreach_message, evidence_snippet

Backward compatibility
----------------------
* No row is updated, deleted, or re-typed. Legacy rows keep their old
  signal_type strings. The new columns are NULL on legacy rows.
* The pre-pivot columns (`location`, `role_title`, `supplier_name`,
  `summary`) stay on the table — read-only for legacy rows, ignored by
  the new pipeline. Removing them now would silently drop history.
* The downgrade re-creates `ck_signals_signal_type` on the original
  three values; if any post-pivot row has a new signal_type (which it
  will, in practice) the constraint creation will fail. That is the
  correct safety: the migration is reversible only against an unused
  schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_logistics_signal_pivot"
down_revision = "0004_platform_sources_and_preferences"
branch_labels = None
depends_on = None


_NEW_TEXT_COLUMNS = (
    "target_customer_type",
    "sector",
    "region",
    "detected_event",
    "why_relevant_for_logistics",
    "potential_logistics_need",
    "urgency",
    "suggested_sales_action",
    "suggested_outreach_message",
    "evidence_snippet",
)


def upgrade() -> None:
    # 1. Drop the enum CHECK so old + new signal_type values coexist.
    op.drop_constraint(
        "ck_signals_signal_type", "detected_signals", type_="check"
    )

    # 2. Logistics-lead text columns. All nullable so legacy rows stay valid.
    op.add_column(
        "detected_signals",
        sa.Column("target_customer_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("sector", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("region", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("detected_event", sa.Text(), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("why_relevant_for_logistics", sa.Text(), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("potential_logistics_need", sa.Text(), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column(
            "recommended_services",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "detected_signals",
        sa.Column("urgency", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("suggested_sales_action", sa.Text(), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("suggested_outreach_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "detected_signals",
        sa.Column("evidence_snippet", sa.Text(), nullable=True),
    )

    # Filter index for the common "give me approved leads in region X"
    # opportunity query. Skip a global GIN on recommended_services for
    # now — analytics on services is not a primary access path yet.
    op.create_index(
        "ix_signals_tenant_region",
        "detected_signals",
        ["tenant_id", "region"],
    )


def downgrade() -> None:
    op.drop_index("ix_signals_tenant_region", table_name="detected_signals")

    op.drop_column("detected_signals", "evidence_snippet")
    op.drop_column("detected_signals", "suggested_outreach_message")
    op.drop_column("detected_signals", "suggested_sales_action")
    op.drop_column("detected_signals", "urgency")
    op.drop_column("detected_signals", "recommended_services")
    op.drop_column("detected_signals", "potential_logistics_need")
    op.drop_column("detected_signals", "why_relevant_for_logistics")
    op.drop_column("detected_signals", "detected_event")
    op.drop_column("detected_signals", "region")
    op.drop_column("detected_signals", "sector")
    op.drop_column("detected_signals", "target_customer_type")

    # Re-add the legacy CHECK. This will fail if any post-pivot row was
    # written with a non-legacy signal_type — that is intentional: a real
    # rollback requires hand-cleaning the table first.
    op.create_check_constraint(
        "ck_signals_signal_type",
        "detected_signals",
        "signal_type IN ('warehouse_opening','supplier_change','hiring_supply_chain_role')",
    )
