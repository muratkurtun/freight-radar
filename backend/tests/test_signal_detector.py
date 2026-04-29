"""Tests for SignalDetector normalization (no LLM calls)."""
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


def test_normalize_rejects_unknown_signal_type():
    out = LlmOutput(prompt_version="v1", signal_type="not_a_real_type", confidence=0.9)
    result = _normalize(out)
    assert result.signal_type is None
    assert result.is_signal is False


def test_normalize_clamps_and_quantizes_confidence():
    over = _normalize(LlmOutput(prompt_version="v1", signal_type=None, confidence=1.7))
    assert over.confidence == Decimal("1.000")
    under = _normalize(LlmOutput(prompt_version="v1", signal_type=None, confidence=-0.4))
    assert under.confidence == Decimal("0.000")
    rounded = _normalize(
        LlmOutput(prompt_version="v1", signal_type=None, confidence=0.123456)
    )
    assert rounded.confidence == Decimal("0.123")


def test_normalize_promotes_known_fields_and_keeps_extras():
    out = LlmOutput(
        prompt_version="v1",
        signal_type="warehouse_opening",
        confidence=0.85,
        extracted_fields={
            "company_name": "  Acme  ",
            "location": "Memphis",
            "role_title": None,
            "supplier_name": "",
            "summary": "Opens new DC",
            "extra_note": "side-channel",
        },
    )
    result = _normalize(out)
    assert result.signal_type == SignalType.WAREHOUSE_OPENING
    assert result.company_name == "Acme"
    assert result.location == "Memphis"
    assert result.role_title is None
    assert result.supplier_name is None  # empty string collapses to None
    assert result.summary == "Opens new DC"
    assert result.extra == {"extra_note": "side-channel"}


def test_signal_detector_uses_injected_verifier():
    stub = _StubVerifier(
        LlmOutput(
            prompt_version="v1",
            signal_type="supplier_change",
            confidence=0.5,
            extracted_fields={"company_name": "Acme"},
        )
    )
    detector = SignalDetector(verifier=stub)
    result = detector.detect(
        source_type="news",
        title="t",
        url=None,
        content="any",
        candidate_hints=None,
    )
    assert stub.calls == 1
    assert result.signal_type == SignalType.SUPPLIER_CHANGE
    assert result.company_name == "Acme"
