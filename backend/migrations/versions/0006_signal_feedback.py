"""sales feedback loop on signals

Revision ID: 0006_signal_feedback
Revises: 0005_logistics_signal_pivot
Create Date: 2026-05-04

What this adds
--------------
A new `signal_feedback` table for tenant-side, sales-team feedback on
detected signals. Distinct from `signal_reviews`:

- `signal_reviews`: admin-binary approve/reject during the pending →
  approved/rejected review transition. Untouched by this migration.
- `signal_feedback`: any authenticated tenant user can record richer
  lifecycle actions (relevant, qualified, contacted, converted, etc.)
  with optional structured reasons and free-form notes.

History is preserved: a (signal, user) pair can have many feedback
rows; the "current team status" is derived at read time from the most
recent row across all users in the tenant.

Backward compatibility
----------------------
* Pure additive — no existing table is touched, no row updated or
  deleted.
* Down-migration drops the new table only; existing signal_reviews,
  detected_signals, etc. remain unchanged.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_signal_feedback"
down_revision = "0005_logistics_signal_pivot"
branch_labels = None
depends_on = None


# Mirror of FeedbackAction enum (app.domain.enums). Validation also lives
# in Pydantic; the CHECK is defense in depth at the DB layer.
_ACTIONS = (
    "relevant",
    "not_relevant",
    "qualified",
    "contacted",
    "converted",
    "dismissed",
    "wrong_company",
    "wrong_sector",
    "not_a_logistics_lead",
)
_REASONS = (
    "wrong_company",
    "wrong_sector",
    "not_a_logistics_lead",
    "duplicate",
    "low_confidence",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "signal_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("detected_signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"action IN ({_quoted(_ACTIONS)})",
            name="ck_signal_feedback_action",
        ),
        sa.CheckConstraint(
            f"reason IS NULL OR reason IN ({_quoted(_REASONS)})",
            name="ck_signal_feedback_reason",
        ),
    )
    # The "what's the team's current status on this lead" query joins
    # signal_feedback by signal_id ORDER BY created_at DESC LIMIT 1.
    # Tenant-scoped index keeps it fast even when the table grows.
    op.create_index(
        "ix_signal_feedback_signal_created",
        "signal_feedback",
        ["signal_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_signal_feedback_tenant_created",
        "signal_feedback",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_signal_feedback_user",
        "signal_feedback",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_feedback_user", table_name="signal_feedback")
    op.drop_index("ix_signal_feedback_tenant_created", table_name="signal_feedback")
    op.drop_index("ix_signal_feedback_signal_created", table_name="signal_feedback")
    op.drop_table("signal_feedback")
