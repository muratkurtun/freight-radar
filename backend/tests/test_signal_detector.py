"""Tests for SignalDetector normalization (no LLM calls).

After the v2 pivot the detector promotes the logistics-lead fields out
of LlmOutput.extracted_fields and enforces the deterministic
guardrails: empty company_name + is_signal=true → drop, LLM
is_signal=false → drop signal_type, confidence clamp + quantize.
"""
from decimal import Decimal

from app.detectors.signal_detector import SignalDetector, _normalize
from app.domain.enums import SignalType
from app.domain.types import LlmOutput


class _StubVerifier:
    """Replaces LlmVerifier; returns a canned LlmOutput for every call."""

    def __init__(self, output: LlmOutput):
        self.output = output
        self.calls = 0

    def verify(self, **_kwargs) -> LlmOutput:
        self.calls += 1
        return self.output


def _llm_output(**fields) -> LlmOutput:
    """Build an LlmOutput with sensible v2 defaults."""
    extracted = {
        "company_name": fields.pop("company_name", "Acme"),
        "target_customer_type": fields.pop("target_customer_type", "exporter"),
        "sector": fields.pop("sector", "food"),
        "region": fields.pop("region", "eu"),
        "detected_event": fields.pop("detected_event", None),
        "why_relevant_for_logistics": fields.pop("why_relevant_for_logistics", None),
        "potential_logistics_need": fields.pop("potential_logistics_need", None),
        "recommended_services": fields.pop("recommended_services", []),
        "urgency": fields.pop("urgency", "medium"),
        "suggested_sales_action": fields.pop("suggested_sales_action", None),
        "suggested_outreach_message": fields.pop(
            "suggested_outreach_message", None
        ),
        "evidence_snippet": fields.pop("evidence_snippet", None),
    }
    extracted.update(fields.pop("extra_extracted", {}))
    return LlmOutput(
        prompt_version=fields.pop("prompt_version", "v2"),
        is_signal=fields.pop("is_signal", True),
        signal_type=fields.pop("signal_type", "export_expansion"),
        confidence=fields.pop("confidence", 0.85),
        extracted_fields=extracted,
    )


# --- signal_type validation ---------------------------------------------

def test_normalize_rejects_unknown_signal_type():
    out = _llm_output(signal_type="not_a_real_type", confidence=0.9)
    result = _normalize(out)
    assert result.signal_type is None
    assert result.is_signal is False


def test_normalize_accepts_v2_signal_type():
    out = _llm_output(signal_type="export_expansion")
    result = _normalize(out)
    assert result.signal_type == SignalType.EXPORT_EXPANSION
    assert result.is_signal is True


# --- confidence normalization -------------------------------------------

def test_normalize_clamps_and_quantizes_confidence():
    over = _normalize(_llm_output(confidence=1.7))
    assert over.confidence == Decimal("1.000")
    under = _normalize(_llm_output(confidence=-0.4))
    assert under.confidence == Decimal("0.000")
    rounded = _normalize(_llm_output(confidence=0.123456))
    assert rounded.confidence == Decimal("0.123")


# --- field promotion + extras --------------------------------------------

def test_normalize_promotes_v2_fields_and_keeps_extras():
    out = _llm_output(
        company_name="  Acme  ",
        target_customer_type="exporter",
        sector="food",
        region="eu",
        detected_event="Acme launched a new export line",
        why_relevant_for_logistics="Long-haul road freight to EU",
        potential_logistics_need="Customs brokerage and TIR",
        recommended_services=["road_freight", "customs_brokerage"],
        urgency="high",
        suggested_sales_action="Reach out to Acme's export manager",
        suggested_outreach_message="Hi, congrats on your EU launch...",
        evidence_snippet="\"Acme will export to Germany next month\"",
        extra_extracted={"side_channel_note": "ignored"},
    )
    result = _normalize(out)
    assert result.signal_type == SignalType.EXPORT_EXPANSION
    assert result.company_name == "Acme"
    assert result.target_customer_type == "exporter"
    assert result.sector == "food"
    assert result.region == "eu"
    assert result.recommended_services == ["road_freight", "customs_brokerage"]
    assert result.urgency == "high"
    assert result.evidence_snippet.startswith('"Acme will export')
    # Anything outside the known v2 schema lands in `extra` for audit.
    assert result.extra == {"side_channel_note": "ignored"}


# --- deterministic guardrails -------------------------------------------

def test_normalize_drops_signal_when_company_missing():
    """company_name empty + is_signal true → not a signal.

    Sales cannot act on 'an unnamed Turkish exporter is expanding' so
    the detector enforces this even if the LLM disagrees.
    """
    out = _llm_output(company_name=None, is_signal=True, signal_type="export_expansion")
    result = _normalize(out)
    assert result.signal_type is None
    assert result.is_signal is False


def test_normalize_drops_signal_when_llm_says_not_signal():
    """LLM is_signal=False overrides any signal_type it accidentally set."""
    out = _llm_output(
        is_signal=False, signal_type="export_expansion", confidence=0.4,
    )
    result = _normalize(out)
    assert result.signal_type is None
    assert result.is_signal is False


# --- detector wiring ----------------------------------------------------

def test_signal_detector_uses_injected_verifier():
    stub = _StubVerifier(_llm_output(signal_type="new_warehouse"))
    detector = SignalDetector(verifier=stub)
    result = detector.detect(
        source_type="news",
        title="t",
        url=None,
        content="any content here long enough to pass any gate",
    )
    assert stub.calls == 1
    assert result.signal_type == SignalType.NEW_WAREHOUSE
    assert result.company_name == "Acme"
