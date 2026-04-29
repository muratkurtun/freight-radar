"""Tests for LlmVerifier helpers and the no-key short-circuit path."""
from app.detectors.llm_verifier import LlmVerifier, _map_to_llm_output, _truncate
from app.detectors.prompts import CURRENT_VERSION


def test_truncate_short_text_is_unchanged():
    assert _truncate("hello", limit=100) == "hello"


def test_truncate_long_text_keeps_head_and_tail():
    text = "A" * 20_000
    out = _truncate(text, limit=12_000)
    assert "\n...\n" in out
    # head + tail boundary preserved (HEAD_KEEP=11500, TAIL_KEEP=500)
    assert out.startswith("A" * 100)
    assert out.endswith("A" * 100)


def test_map_to_llm_output_handles_valid_payload():
    out = _map_to_llm_output(
        {
            "signal_type": "warehouse_opening",
            "confidence": 0.9,
            "extracted_fields": {"company_name": "Acme"},
        }
    )
    assert out.signal_type == "warehouse_opening"
    assert out.confidence == 0.9
    assert out.extracted_fields == {"company_name": "Acme"}


def test_map_to_llm_output_collapses_invalid_fields():
    out = _map_to_llm_output(
        {
            "signal_type": "wrong_type",
            "confidence": "not_a_number",
            "extracted_fields": "not_a_dict",
        }
    )
    assert out.signal_type is None
    assert out.confidence == 0.0
    assert out.extracted_fields == {}


def test_verifier_short_circuits_when_no_api_key(monkeypatch):
    """With OPENAI_API_KEY unset, LlmVerifier must not call the API.

    conftest.py already seeds OPENAI_API_KEY="". Constructing a verifier
    with no client must succeed and verify() must return an empty
    LlmOutput marked with the current prompt version.
    """
    # Belt + suspenders: ensure the env is empty even if a higher-priority
    # test env var leaks in.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Settings is cached; clear the cache so the new env is observed.
    from app.config import get_settings

    get_settings.cache_clear()

    verifier = LlmVerifier()
    result = verifier.verify(
        source_type="news",
        title="t",
        url=None,
        content="content",
        candidate_hints=None,
    )
    assert result.signal_type is None
    assert result.confidence == 0.0
    assert result.extracted_fields == {}
    assert result.prompt_version == CURRENT_VERSION
