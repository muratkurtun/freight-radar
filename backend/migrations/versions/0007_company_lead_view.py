"""company entity + signal→company link + idempotent backfill

Revision ID: 0007_company_lead_view
Revises: 0006_signal_feedback
Create Date: 2026-05-04

What this adds
--------------
The `companies` table — tenant-scoped, no global registry. Each
detected_signal that names a company gets linked via a new
`detected_signals.company_id` column (nullable; legacy rows + signals
where the LLM did not extract a company stay NULL).

Backfill
--------
Runs inside this migration in pure Python over the alembic
connection. Idempotent: companies are inserted with ON CONFLICT DO
NOTHING on (tenant_id, normalized_name), and signals are updated only
where company_id IS NULL. Re-running the migration after a partial
failure is safe.

Backward compatibility
----------------------
* No row is deleted. company_name on detected_signals stays populated.
* The new column is nullable; legacy rows or signals with no company
  remain valid.
* Down-migration drops the column and the table. detected_signals
  rows that had been linked simply lose their FK pointer (CASCADE
  isn't used here — we use SET NULL on company drop, but downgrade
  drops the column outright so this isn't surfaced).
"""
from __future__ import annotations

import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_company_lead_view"
down_revision = "0006_signal_feedback"
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------
# Inline copy of normalize_company_name from app/core/normalization.py.
# Migrations must not import from `app.*` (the app stack may not be
# importable during alembic upgrades from a stripped image), so we mirror
# the rules here. KEEP IN SYNC: any change to normalization.py needs an
# accompanying re-backfill migration.
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s&]+", re.UNICODE)
_COMPANY_SUFFIXES: tuple[str, ...] = (
    "anonim sirketi", "limited sirketi", "as", "ltd sti", "sti",
    "ltd", "limited", "inc", "incorporated", "corp", "corporation",
    "co", "company", "llc", "plc", "gmbh", "sa", "spa", "bv",
)
_TR_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g",
        "ı": "i", "İ": "i", "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
    }
)


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    folded = value.translate(_TR_FOLD)
    nfkd = unicodedata.normalize("NFKD", folded)
    ascii_like = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    text = _WS.sub(" ", ascii_like).strip().lower()
    if not text:
        return ""
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    if not text:
        return ""
    for suffix in _COMPANY_SUFFIXES:
        if text.endswith(" " + suffix):
            text = text[: -(len(suffix) + 1)].strip()
            break
    return text


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=40), nullable=True),
        sa.Column("region", sa.String(length=40), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
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
        sa.UniqueConstraint(
            "tenant_id", "normalized_name", name="uq_companies_tenant_normalized"
        ),
    )
    op.create_index("ix_companies_tenant", "companies", ["tenant_id"])
    op.create_index(
        "ix_companies_tenant_sector", "companies", ["tenant_id", "sector"]
    )

    op.add_column(
        "detected_signals",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_signals_tenant_company",
        "detected_signals",
        ["tenant_id", "company_id"],
    )

    _backfill()


def _backfill() -> None:
    """Idempotent backfill: build companies from existing signals,
    link them. Safe to re-run because:
      * INSERT uses ON CONFLICT DO NOTHING on (tenant_id, normalized_name)
      * UPDATE only touches signals where company_id IS NULL
    """
    conn = op.get_bind()

    # Pull (tenant_id, raw company_name, first sector/region) per
    # distinct company occurrence. The "first" sector/region uses the
    # row with MIN(created_at) so re-runs deterministically pick the
    # same seed values.
    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT ON (s.tenant_id, s.company_name)
                   s.tenant_id,
                   s.company_name,
                   s.sector,
                   s.region
            FROM detected_signals s
            WHERE s.company_name IS NOT NULL
              AND TRIM(s.company_name) <> ''
            ORDER BY s.tenant_id, s.company_name, s.created_at ASC
            """
        )
    ).all()

    insert_sql = sa.text(
        """
        INSERT INTO companies (id, tenant_id, name, normalized_name,
                               sector, region, created_at, updated_at)
        VALUES (gen_random_uuid(), :tenant_id, :name, :normalized_name,
                :sector, :region, now(), now())
        ON CONFLICT (tenant_id, normalized_name) DO NOTHING
        """
    )
    update_sql = sa.text(
        """
        UPDATE detected_signals s
           SET company_id = c.id
          FROM companies c
         WHERE s.tenant_id = :tenant_id
           AND s.company_id IS NULL
           AND c.tenant_id = :tenant_id
           AND c.normalized_name = :normalized_name
           AND TRIM(s.company_name) <> ''
           -- match against the same normalization so name variants
           -- ("ABC Foods", "ABC FOODS Ltd") collapse onto one company
           AND s.company_name IS NOT NULL
           AND lower(regexp_replace(
                   translate(s.company_name,
                             'ÇçĞğİıÖöŞşÜü',
                             'CcGgIiOoSsUu'),
                   '[^\\w\\s&]+', ' ', 'g'
               )) ~ ('(^|\\s)' || :normalized_name || '($|\\s)')
        """
    )

    seen: set[tuple[str, str]] = set()
    for tenant_id, raw_name, sector, region in rows:
        normalized = _normalize(raw_name)
        if not normalized:
            continue
        key = (str(tenant_id), normalized)
        if key in seen:
            continue
        seen.add(key)
        conn.execute(
            insert_sql,
            {
                "tenant_id": tenant_id,
                "name": raw_name.strip(),
                "normalized_name": normalized,
                "sector": sector,
                "region": region,
            },
        )

    # Link signals back to their companies. The Python-side
    # normalization is authoritative — we do an in-Python loop so the
    # SQL doesn't need to recreate the full normalization (suffix
    # stripping etc.) inline.
    link_one = sa.text(
        """
        UPDATE detected_signals
           SET company_id = (
               SELECT c.id FROM companies c
                WHERE c.tenant_id = detected_signals.tenant_id
                  AND c.normalized_name = :normalized_name
                LIMIT 1
           )
         WHERE tenant_id = :tenant_id
           AND company_id IS NULL
           AND id = :signal_id
        """
    )
    signal_rows = conn.execute(
        sa.text(
            """
            SELECT id, tenant_id, company_name
              FROM detected_signals
             WHERE company_id IS NULL
               AND company_name IS NOT NULL
               AND TRIM(company_name) <> ''
            """
        )
    ).all()
    for signal_id, tenant_id, company_name in signal_rows:
        normalized = _normalize(company_name)
        if not normalized:
            continue
        conn.execute(
            link_one,
            {
                "signal_id": signal_id,
                "tenant_id": tenant_id,
                "normalized_name": normalized,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_signals_tenant_company", table_name="detected_signals")
    op.drop_column("detected_signals", "company_id")
    op.drop_index("ix_companies_tenant_sector", table_name="companies")
    op.drop_index("ix_companies_tenant", table_name="companies")
    op.drop_table("companies")
