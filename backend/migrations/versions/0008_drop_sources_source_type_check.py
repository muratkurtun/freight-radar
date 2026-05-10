"""drop ck_sources_source_type to allow new SourceType values

Revision ID: 0008_drop_sources_source_type_check
Revises: 0007_company_lead_view
Create Date: 2026-05-10

What this changes
-----------------
The `sources` table CHECK constraint hardcoded the original three
SourceType values:

    CHECK (source_type IN ('news','job_board','company_website'))

That blocks Phase 12.5 from introducing `news_html` (a thin
semantic split for HTML-listing news publications, reusing the
existing CompanyWebsiteCollector). Phase 5 already removed the
equivalent CHECK on detected_signals.signal_type for the same
reason — the SourceType enum is the write authority from now on.

Backward compatibility
----------------------
* No row is updated, deleted, or re-typed.
* Existing rows already carry one of the three legal values, so
  dropping the constraint does not invalidate any data.
* Reads stay tolerant of unknown values — analytics queries (e.g.
  /feedback/stats/by-source) join on the column without coercing it
  back through the enum.

Downgrade caveat
----------------
The downgrade re-adds the original CHECK on the original three
values. If any post-upgrade row carries `news_html` (or any future
addition) the constraint creation will fail. That is intentional:
a real rollback requires hand-cleaning the table first. README
flags this for operators.
"""
from alembic import op

revision = "0008_drop_sources_source_type_check"
down_revision = "0007_company_lead_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_sources_source_type", "sources", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_sources_source_type",
        "sources",
        "source_type IN ('news','job_board','company_website')",
    )
