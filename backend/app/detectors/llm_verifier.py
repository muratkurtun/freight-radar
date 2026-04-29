"""LLM-based verifier for rule-based candidates.

Input:  a raw item that the candidate_detector has already flagged as
        plausibly interesting (possibly with hints about which signal
        types matched).
Output: a permissive LlmOutput — signal_type is one of the three defined
        values or None, confidence is a float in [0, 1], extracted_fields
        is a dict (fields may be missing / null).

This is the ONLY place in the backend that spends LLM tokens. Everything
before (collector, content-hash dedupe, candidate_detector) is cheap
Python; everything after (signal_detector normalization, repository
writes) is local work on the LLM's output. Keeping the LLM call
isolated here means:
  - a single knob for model/temperature/truncation
  - one retry policy
  - easy to mock in tests and easy to swap for a different provider

Failure policy
--------------
The verifier never raises. Transport errors, rate limits, malformed
JSON after retry — all of them log a warning and return an "empty"
LlmOutput (signal_type=None). The pipeline treats that as "not a
signal" and moves on. A noisy LLM must not take down a collection run.
"""
from __future__ import annotations

import time
from typing import Iterable

from openai import APIError

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.detectors.llm_client import LLMClient
from app.detectors.prompts import CURRENT_VERSION, SYSTEM_PROMPT_V1, build_user_prompt
from app.domain.enums import SignalType
from app.domain.types import LlmOutput

logger = get_logger(__name__)

# Cost controls. The crawler already caps raw content at 20,000 chars; we
# truncate more aggressively here because the LLM bill scales with input
# tokens and the opening paragraphs carry the signal ~always.
MAX_INPUT_CHARS = 12_000
HEAD_KEEP = MAX_INPUT_CHARS - 500
TAIL_KEEP = 500

# Deterministic classification. Temperature > 0 would let the same
# article flip between signal / no-signal on retry, which breaks
# dedupe and review workflows downstream.
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 512         # the JSON response is < 300 tokens in practice

# One retry is enough in practice: if the first call returns invalid
# JSON at temperature 0, a second call with a stricter nudge almost
# always fixes it. More than one retry burns tokens without payoff.
MAX_PARSE_RETRIES = 1
RETRY_BACKOFF_SECONDS = 0.5

_VALID_SIGNAL_TYPES: frozenset[str] = frozenset(t.value for t in SignalType)


class LlmVerifier:
    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        max_input_chars: int = MAX_INPUT_CHARS,
    ):
        self._max_input_chars = max_input_chars
        if client is not None:
            self._client: LLMClient | None = client
            self._disabled = False
            return
        # Explicit short-circuit: when no API key is configured, skip the
        # LLM step entirely instead of letting LLMClient raise on every
        # item. The pipeline treats the empty LlmOutput as "not a signal".
        if not get_settings().openai_api_key:
            self._client = None
            self._disabled = True
            logger.info("LLM verifier disabled (OPENAI_API_KEY not set)")
            return
        self._client = LLMClient()
        self._disabled = False

    def verify(
        self,
        *,
        source_type: str,
        title: str | None,
        url: str | None,
        content: str,
        candidate_hints: Iterable[SignalType] | None = None,
    ) -> LlmOutput:
        if self._disabled:
            return LlmOutput(prompt_version=CURRENT_VERSION)
        truncated = _truncate(content, self._max_input_chars)
        hints = [s.value for s in candidate_hints] if candidate_hints else None
        user_prompt = build_user_prompt(
            source_type=source_type,
            title=title,
            url=url,
            content=truncated,
            candidate_hints=hints,
        )
        payload = self._complete_with_retry(user_prompt)
        if payload is None:
            return LlmOutput(prompt_version=CURRENT_VERSION)
        return _map_to_llm_output(payload)

    def _complete_with_retry(self, user_prompt: str) -> dict | None:
        prompt = user_prompt
        last_error: Exception | None = None
        for attempt in range(1, MAX_PARSE_RETRIES + 2):
            try:
                return self._client.complete_json(
                    system=SYSTEM_PROMPT_V1,
                    user=prompt,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=TEMPERATURE,
                )
            except AppError as e:
                last_error = e
                if e.code != "llm_invalid_json":
                    # config / auth / other app-level error: no retry
                    break
                logger.warning(
                    "LLM returned invalid JSON (attempt %s/%s); retrying with strict nudge",
                    attempt, MAX_PARSE_RETRIES + 1,
                )
                prompt = _strict_retry_prompt(user_prompt)
                time.sleep(RETRY_BACKOFF_SECONDS)
            except APIError as e:
                # Transport / rate-limit error. The SDK already does
                # provider-level retries for 5xx; anything that reaches
                # here is worth giving up on for this item.
                last_error = e
                break
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.exception("Unexpected LLM verifier error")
                break
        logger.warning("LLM verifier gave up: %s", last_error)
        return None


def _truncate(content: str, limit: int) -> str:
    """Keep the lede (head) and a short tail.

    News ledes almost always carry the signal; the tail is insurance for
    the rare article where the punchline is at the end. A visible `...`
    between the two halves tells the LLM the text was clipped so it does
    not treat the boundary as semantic."""
    content = content.strip()
    if len(content) <= limit:
        return content
    return content[:HEAD_KEEP] + "\n...\n" + content[-TAIL_KEEP:]


def _strict_retry_prompt(original: str) -> str:
    return (
        original
        + "\n\nSTRICT: Respond with ONE JSON object only. "
        "No markdown, no code fences, no explanation. "
        'If you cannot comply, respond exactly: '
        '{"signal_type": null, "confidence": 0, "extracted_fields": {}}.'
    )


def _map_to_llm_output(payload: dict) -> LlmOutput:
    """Turn the parsed JSON into a permissive LlmOutput.

    Invalid values do NOT raise — they collapse to sensible nulls. The
    downstream normalizer in signal_detector still has to validate, but
    by the time it runs the shape is already predictable."""
    raw_type = payload.get("signal_type")
    signal_type = (
        raw_type
        if isinstance(raw_type, str) and raw_type in _VALID_SIGNAL_TYPES
        else None
    )

    raw_conf = payload.get("confidence", 0.0)
    try:
        confidence = float(raw_conf)
    except (TypeError, ValueError):
        confidence = 0.0

    extracted = payload.get("extracted_fields")
    if not isinstance(extracted, dict):
        extracted = {}

    return LlmOutput(
        prompt_version=CURRENT_VERSION,
        signal_type=signal_type,
        confidence=confidence,
        extracted_fields=extracted,
    )
