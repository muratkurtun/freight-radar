"""Tests for the company-lead view.

Covers three layers:

  * normalize_company_name — pure deterministic helper used by both
    the runtime get-or-create path and the 0007 backfill.
  * CompanyRepository.get_or_create_by_normalized_name — fake-Session
    unit tests for tenant scoping, idempotency, fill-if-NULL.
  * Aggregation specs (derive_team_status / derive_lead_score /
    derive_lead_tier) — these mirror the SQL CASE expressions in
    company_leads.py. The SQL itself is locked to these helpers via
    code review; an integration test against Postgres would lock it
    further but is out of scope for this phase.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.core.normalization import normalize_company_name
from app.domain.models import Company
from app.repositories.companies import CompanyRepository
from app.repositories.company_leads import (
    derive_lead_score,
    derive_lead_tier,
    derive_team_status,
)


# --------------------------------------------------------------------------
# normalize_company_name
# --------------------------------------------------------------------------


def test_normalize_lowercases_and_trims():
    assert normalize_company_name("  ABC Foods  ") == "abc foods"


def test_normalize_collapses_internal_whitespace():
    assert normalize_company_name("ABC   Foods\tInc") == "abc foods"


def test_normalize_strips_punctuation_keeps_ampersand():
    """Ampersands distinguish 'P&G' from 'PG' so we keep them; other
    punctuation is collapsed to whitespace."""
    assert normalize_company_name("P&G, Inc.") == "p&g"
    assert normalize_company_name("Smith-Foods, LLC") == "smith foods"


def test_normalize_turkish_diacritics_folded():
    assert normalize_company_name("Şirin İhracat") == "sirin ihracat"


def test_normalize_strips_one_legal_suffix_only():
    """One trailing suffix max — repeated suffixes do NOT collapse to
    empty (which would silently merge unrelated companies)."""
    assert normalize_company_name("Acme Ltd") == "acme"
    # 'ltd ltd' → strip one 'ltd' → 'acme ltd'  (still distinct)
    assert normalize_company_name("Acme Ltd Ltd") == "acme ltd"


def test_normalize_empty_inputs_return_empty_string():
    assert normalize_company_name(None) == ""
    assert normalize_company_name("") == ""
    assert normalize_company_name("   ") == ""
    # Punctuation-only — once collapsed, nothing remains.
    assert normalize_company_name("---") == ""


# --------------------------------------------------------------------------
# CompanyRepository.get_or_create_by_normalized_name
# --------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, owner: "_FakeSession"):
        self.owner = owner

    def where(self, *_clauses):
        return self

    def order_by(self, *_clauses):
        return self


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Just enough Session API to drive get_or_create paths."""

    def __init__(self, existing: Company | None = None):
        self._existing = existing
        self.added: list[Company] = []
        self.flushed = 0

    def execute(self, _stmt):
        return _FakeResult(self._existing)

    def add(self, instance: Company):
        self.added.append(instance)

    def flush(self):
        self.flushed += 1


def test_get_or_create_skips_when_normalized_empty():
    db = _FakeSession(existing=None)
    repo = CompanyRepository(db, uuid4())  # type: ignore[arg-type]

    assert repo.get_or_create_by_normalized_name(raw_name="") is None
    assert repo.get_or_create_by_normalized_name(raw_name="   ") is None
    assert repo.get_or_create_by_normalized_name(raw_name="---") is None
    assert db.added == []


def test_get_or_create_inserts_new_company_with_sector_region():
    tenant_id = uuid4()
    db = _FakeSession(existing=None)
    repo = CompanyRepository(db, tenant_id)  # type: ignore[arg-type]

    created = repo.get_or_create_by_normalized_name(
        raw_name="ABC Foods Ltd",
        sector="food",
        region="eu",
    )

    assert created is not None
    assert created.tenant_id == tenant_id
    assert created.name == "ABC Foods Ltd"
    assert created.normalized_name == "abc foods"
    assert created.sector == "food"
    assert created.region == "eu"
    assert db.added == [created]


def test_get_or_create_returns_existing_without_creating_again():
    tenant_id = uuid4()
    existing = Company(
        tenant_id=tenant_id,
        name="ABC Foods",
        normalized_name="abc foods",
        sector="food",
        region="eu",
    )
    db = _FakeSession(existing=existing)
    repo = CompanyRepository(db, tenant_id)  # type: ignore[arg-type]

    out = repo.get_or_create_by_normalized_name(
        raw_name="abc foods ltd",
        sector="food",
        region="eu",
    )

    assert out is existing
    assert db.added == []


def test_get_or_create_fills_null_sector_and_region_only():
    """First-set wins: an existing curated value is never overwritten,
    but a NULL field gets backfilled from the new signal."""
    tenant_id = uuid4()
    existing = Company(
        tenant_id=tenant_id,
        name="ABC Foods",
        normalized_name="abc foods",
        sector=None,        # ← gets backfilled
        region="eu",        # ← stays as-is
    )
    db = _FakeSession(existing=existing)
    repo = CompanyRepository(db, tenant_id)  # type: ignore[arg-type]

    out = repo.get_or_create_by_normalized_name(
        raw_name="ABC Foods",
        sector="food",       # incoming
        region="turkey",     # incoming, but should NOT overwrite 'eu'
    )

    assert out is existing
    assert existing.sector == "food"
    assert existing.region == "eu"
    # Updated_at touched once for the partial backfill.
    assert db.flushed == 1


def test_get_or_create_no_change_for_already_complete_company():
    """No flush when nothing needs to change."""
    tenant_id = uuid4()
    existing = Company(
        tenant_id=tenant_id,
        name="ABC Foods",
        normalized_name="abc foods",
        sector="food",
        region="eu",
    )
    db = _FakeSession(existing=existing)
    repo = CompanyRepository(db, tenant_id)  # type: ignore[arg-type]

    out = repo.get_or_create_by_normalized_name(
        raw_name="ABC Foods",
        sector="food",
        region="eu",
    )

    assert out is existing
    assert db.flushed == 0


# --------------------------------------------------------------------------
# Spec helpers (mirror the SQL CASE expressions)
# --------------------------------------------------------------------------


def _counts(**kwargs) -> dict[str, int]:
    """Build a feedback breakdown with sensible defaults."""
    base = dict(
        converted_count=0, contacted_count=0, qualified_count=0,
        relevant_count=0, dismissed_count=0, not_relevant_count=0,
        wrong_company_count=0, wrong_sector_count=0,
        not_a_logistics_lead_count=0,
    )
    base.update(kwargs)
    return base


def test_status_is_new_with_no_feedback():
    assert derive_team_status(**_counts()) == "new"


def test_status_priority_converted_wins():
    """Even with negatives present, a single converted dominates."""
    assert (
        derive_team_status(
            **_counts(converted_count=1, dismissed_count=10)
        )
        == "converted"
    )


def test_status_priority_chain():
    """contacted > qualified > relevant when no converted."""
    assert (
        derive_team_status(**_counts(contacted_count=1, qualified_count=5))
        == "contacted"
    )
    assert (
        derive_team_status(**_counts(qualified_count=1, relevant_count=5))
        == "qualified"
    )
    assert derive_team_status(**_counts(relevant_count=1)) == "relevant"


def test_status_negative_majority_dismissed_wins():
    """No positives, dismissed is the most-frequent negative."""
    assert (
        derive_team_status(
            **_counts(dismissed_count=3, not_relevant_count=1)
        )
        == "dismissed"
    )


def test_status_negative_majority_not_relevant_cluster_wins():
    """The corrective wrong_* actions count toward not_relevant."""
    assert (
        derive_team_status(
            **_counts(
                dismissed_count=1,
                not_relevant_count=1,
                wrong_company_count=1,
                wrong_sector_count=1,
            )
        )
        == "not_relevant"
    )


def test_status_dismissed_ties_break_to_dismissed():
    """SQL CASE: dismissed >= cluster AND dismissed > 0 → 'dismissed'.
    Tie → dismissed."""
    assert (
        derive_team_status(
            **_counts(dismissed_count=2, not_relevant_count=2)
        )
        == "dismissed"
    )


def test_lead_score_clamps_to_100():
    """A 95-point signal with the recent-activity bonus would land at
    105; the spec clamps to 100."""
    assert derive_lead_score(max_signal_score=95, recent_signal_count=2) == 100


def test_lead_score_recent_bonus_only_at_two_or_more():
    assert derive_lead_score(max_signal_score=60, recent_signal_count=1) == 60
    assert derive_lead_score(max_signal_score=60, recent_signal_count=2) == 70


def test_lead_score_zero_for_no_signals():
    assert derive_lead_score(max_signal_score=0, recent_signal_count=0) == 0


def test_lead_tier_thresholds():
    assert derive_lead_tier(80) == "hot"
    assert derive_lead_tier(75) == "hot"  # boundary
    assert derive_lead_tier(74) == "warm"
    assert derive_lead_tier(50) == "warm"  # boundary
    assert derive_lead_tier(49) == "low"
    assert derive_lead_tier(0) == "low"
