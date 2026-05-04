"""Tests for LlmVerifier helpers and the no-key short-circuit path.

The verifier is the only place in the backend that spends LLM tokens,
so the cost guardrails (no-key short-circuit, content too short, missing
title+content) need explicit regression coverage.
"""
from app.detectors.llm_verifier import (
    LlmVerifier,
    _coerce_service_list,
    _map_to_llm_output,
    _truncate,
)
from app.detectors.prompts import CURRENT_VERSION


# --- truncation ---------------------------------------------------------

def test_truncate_short_text_is_unchanged():
    assert _truncate("hello", limit=100) == "hello"


def test_truncate_long_text_keeps_head_and_tail():
    text = "A" * 20_000
    out = _truncate(text, limit=12_000)
    assert "\n...\n" in out
    # head + tail boundary preserved (HEAD_KEEP=11500, TAIL_KEEP=500)
    assert out.startswith("A" * 100)
    assert out.endswith("A" * 100)


# --- payload mapping ----------------------------------------------------

def test_map_to_llm_output_handles_valid_v2_payload():
    out = _map_to_llm_output(
        {
            "is_signal": True,
            "signal_type": "export_expansion",
            "confidence": 0.78,
            "company_name": "Acme Foods",
            "target_customer_type": "exporter",
            "sector": "food",
            "region": "eu",
            "detected_event": "Launched EU sales channel",
            "why_relevant_for_logistics": "Cross-border road freight needed",
            "potential_logistics_need": "Customs brokerage + TIR",
            "recommended_services": ["road_freight", "customs_brokerage"],
            "urgency": "medium",
            "suggested_sales_action": "Reach out to export manager",
            "suggested_outreach_message": "Congrats on EU launch...",
            "evidence_snippet": "Acme will start shipments in June.",
        }
    )
    assert out.is_signal is True
    assert out.signal_type == "export_expansion"
    assert out.confidence == 0.78
    assert out.extracted_fields["company_name"] == "Acme Foods"
    assert out.extracted_fields["region"] == "eu"
    assert out.extracted_fields["recommended_services"] == [
        "road_freight",
        "customs_brokerage",
    ]


def test_map_to_llm_output_collapses_invalid_fields():
    out = _map_to_llm_output(
        {
            "is_signal": "true",  # truthy non-bool, coerced
            "signal_type": "wrong_type",
            "confidence": "not_a_number",
            "company_name": 42,  # non-string
            "urgency": "BANANAS",  # off-vocab
            "recommended_services": ["road_freight", "made_up_service"],
        }
    )
    assert out.signal_type is None  # off-vocab type collapses
    assert out.confidence == 0.0
    # Out-of-vocab service dropped silently
    assert out.extracted_fields["recommended_services"] == ["road_freight"]
    # Off-vocab urgency collapses to None
    assert out.extracted_fields["urgency"] is None


def test_recommended_services_drops_non_strings():
    assert _coerce_service_list(["road_freight", 7, None, "warehousing"]) == [
        "road_freight",
        "warehousing",
    ]


def test_recommended_services_dedupes():
    assert _coerce_service_list(
        ["road_freight", "ROAD_FREIGHT", "road_freight"]
    ) == ["road_freight"]


# --- no-key short-circuit ----------------------------------------------

def test_verifier_short_circuits_when_no_api_key(monkeypatch):
    """conftest.py already seeds OPENAI_API_KEY=''. Constructing the
    verifier with no client must succeed and verify() must return an
    empty LlmOutput marked with the current prompt version — no API
    call, no exception."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()

    verifier = LlmVerifier()
    result = verifier.verify(
        source_type="news",
        title="t",
        url=None,
        content="content long enough to pass min-length",
        preferences=None,
    )
    assert result.is_signal is False
    assert result.signal_type is None
    assert result.confidence == 0.0
    assert result.extracted_fields == {}
    assert result.prompt_version == CURRENT_VERSION


# --- content guards -----------------------------------------------------

class _RecordingClient:
    """Counts calls to verify the verifier short-circuited correctly."""

    def __init__(self):
        self.calls = 0

    def complete_json(self, **_kwargs):
        self.calls += 1
        return {"is_signal": False, "signal_type": None, "confidence": 0}


def test_verifier_skips_when_title_and_content_missing():
    client = _RecordingClient()
    verifier = LlmVerifier(client=client)
    result = verifier.verify(
        source_type="news", title=None, url=None, content="", preferences=None,
    )
    assert client.calls == 0
    assert result.is_signal is False


def test_verifier_skips_when_content_too_short():
    """Below MIN_USEFUL_CONTENT_CHARS the verifier refuses without a call."""
    client = _RecordingClient()
    verifier = LlmVerifier(client=client)
    result = verifier.verify(
        source_type="news",
        title="t",
        url=None,
        content="Tiny.",
        preferences=None,
    )
    assert client.calls == 0
    assert result.is_signal is False
