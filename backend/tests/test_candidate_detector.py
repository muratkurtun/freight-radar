"""Tests for the v2 broad-gate candidate filter.

Post-pivot the gate is recall-first: a single keyword OR-pattern over a
normalized title+content. The LLM (constrained by tenant preferences)
does the per-type classification. Tests here lock the cost guardrails:

  - empty / very short content                → False (no LLM)
  - non-business news                         → False
  - logistics-relevant business item          → True
  - JOB_BOARD with any payload                → True
"""
from app.detectors.candidate_detector import is_business_relevant, should_call_llm
from app.domain.enums import SourceType


# --- empty / short content guards ----------------------------------------

def test_empty_content_returns_false():
    assert is_business_relevant(
        source_type=SourceType.NEWS.value, title=None, content=""
    ) is False


def test_short_content_returns_false():
    """Below MIN_GATE_CONTENT_CHARS the gate refuses regardless of keywords."""
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title="ABC opens",
        content="Short.",
    ) is False


# --- positive matches ----------------------------------------------------

def test_factory_expansion_news_matches():
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title="Acme opens new factory in Bursa",
        content="The company inaugurated a new plant for export production.",
    ) is True


def test_export_expansion_passes_gate():
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title="Globex begins exporting to Germany",
        content="Globex announced it will expand exports across the European market.",
    ) is True


def test_turkish_keyword_matches_after_normalization():
    """`yeni depo` (TR) should hit the gate even with diacritics dropped.

    The content is padded above MIN_GATE_CONTENT_CHARS so this test
    locks the keyword + folding pipeline, not the length guard."""
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title=None,
        content=(
            "Şirket Bursa'da yeni depo açılışını duyurdu. "
            "Açılış törenine yöneticiler katıldı."
        ),
    ) is True


def test_hiring_logistics_role_passes_gate():
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title="Acme is hiring a logistics manager",
        content="The company is looking for a logistics manager to join its team.",
    ) is True


# --- negative matches ----------------------------------------------------

def test_lifestyle_news_does_not_match():
    """Sports / opinion / lifestyle text with no business keywords is
    dropped before the LLM."""
    assert is_business_relevant(
        source_type=SourceType.NEWS.value,
        title="A weekend in Cappadocia",
        content="Visitors enjoyed hot air balloon rides over the valleys.",
    ) is False


# --- job-board behavior --------------------------------------------------

def test_job_board_passes_with_any_payload():
    """Every job posting is potentially a hiring signal; the verifier
    decides which kind. The gate just guards against totally empty
    rows."""
    assert is_business_relevant(
        source_type=SourceType.JOB_BOARD.value,
        title="Open positions",
        content="We are reviewing candidates.",
    ) is True


def test_job_board_with_no_content_blocked():
    assert is_business_relevant(
        source_type=SourceType.JOB_BOARD.value, title=None, content=""
    ) is False


# --- public API alias ----------------------------------------------------

def test_should_call_llm_alias_matches_is_business_relevant():
    args = dict(
        source_type=SourceType.NEWS.value,
        title="Acme opens new warehouse",
        content="The new facility will increase capacity for European exports.",
    )
    assert should_call_llm(**args) == is_business_relevant(**args)
