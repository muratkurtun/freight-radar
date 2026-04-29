"""Unit tests for the rule-based candidate prefilter.

The detector is pure: text in, list of Candidate out. Cheap to test
and the safety net for changes to the keyword lists / negation rules.
"""
from app.detectors.candidate_detector import (
    detect_candidate_signals,
    should_call_llm,
)
from app.domain.enums import SignalType, SourceType


def _types(candidates) -> set[str]:
    return {c.signal_type.value for c in candidates}


# ----- warehouse_opening ---------------------------------------------------

def test_warehouse_opening_positive_english():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme opens new distribution center in Memphis",
        content="Ribbon cutting today.",
    )
    assert SignalType.WAREHOUSE_OPENING.value in _types(cands)


def test_warehouse_opening_positive_turkish():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title=None,
        content="Şirket bu hafta yeni depo açılışı düzenledi.",
    )
    assert SignalType.WAREHOUSE_OPENING.value in _types(cands)


def test_warehouse_opening_negative_phrase_blocks():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme warehouse closes in Memphis",
        content="The warehouse closed yesterday after layoffs.",
    )
    assert SignalType.WAREHOUSE_OPENING.value not in _types(cands)


# ----- supplier_change -----------------------------------------------------

def test_supplier_change_positive():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme partners with NewLogistics for European deliveries",
        content="The deal includes a multi-year supply agreement.",
    )
    assert SignalType.SUPPLIER_CHANGE.value in _types(cands)


def test_supplier_change_pr_phrase_does_not_trigger():
    """Supplier conference / awards are PR events, not actual changes."""
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme hosts annual Supplier Conference",
        content="The supplier event will run for two days.",
    )
    assert SignalType.SUPPLIER_CHANGE.value not in _types(cands)


# ----- hiring_supply_chain_role -------------------------------------------

def test_hiring_supply_chain_news_needs_verb_and_role():
    """On news sources both a hiring verb AND a role keyword must hit."""
    role_only = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme appoints new logistics manager",
        content="The company restructures its supply chain.",
    )
    assert SignalType.HIRING_SUPPLY_CHAIN_ROLE.value not in _types(role_only)

    role_and_verb = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme is hiring a logistics manager",
        content="Open position for a supply chain analyst.",
    )
    assert SignalType.HIRING_SUPPLY_CHAIN_ROLE.value in _types(role_and_verb)


def test_hiring_supply_chain_job_board_needs_only_role():
    """Job-board items are implicitly 'we are hiring' — role keyword is enough."""
    cands = detect_candidate_signals(
        source_type=SourceType.JOB_BOARD.value,
        title="Logistics Coordinator",
        content="Responsible for fleet operations across the EU.",
    )
    assert SignalType.HIRING_SUPPLY_CHAIN_ROLE.value in _types(cands)


# ----- empty / null --------------------------------------------------------

def test_empty_haystack_returns_empty():
    assert detect_candidate_signals(
        source_type=SourceType.NEWS.value, title=None, content=""
    ) == []


def test_no_keyword_match_returns_empty():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Quarterly results steady",
        content="Revenue flat year over year.",
    )
    assert cands == []
    assert should_call_llm(cands) is False


def test_should_call_llm_returns_true_when_match():
    cands = detect_candidate_signals(
        source_type=SourceType.NEWS.value,
        title="Acme opens new warehouse in Houston",
        content="",
    )
    assert should_call_llm(cands) is True
