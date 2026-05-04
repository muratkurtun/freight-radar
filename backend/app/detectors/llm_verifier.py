"""LLM-based verifier — turns a raw item into a structured logistics
sales lead candidate.

Input:  one raw item (title + content + url) plus the tenant's
        targeting preferences. Tenant prefs go *into the prompt* so the
        LLM can short-circuit signals that fall outside the tenant's
        customer / sector / region / focus profile.
Output: a permissive LlmOutput. Field validation is permissive at this
        layer — invalid values collapse to safe nulls. SignalDetector
        does the strict normalization.

This is the only place in the backend that spends LLM tokens.
Everything before (collector, content-hash dedupe, candidate gate) is
free Python; everything after (signal_detector, repository writes) is
local work on the LLM's output. Keeping the LLM call isolated here:
- one knob for model / temperature / truncation
- one retry policy
- one place to mock in tests

Failure policy
--------------
The verifier never raises. Transport errors, rate limits, malformed
JSON after retry — all log a warning and return an empty LlmOutput
(is_signal=False). The pipeline treats that as "not a signal" and the
item stays unprocessed_at NULL so a later run can retry.
"""
from __future__ import annotations

import time

from openai import APIError

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.detectors.llm_client import LLMClient
from app.detectors.prompts import (
    CURRENT_VERSION,
    SYSTEM_PROMPT_V2,
    build_user_prompt_v2,
)
from app.domain.enums import RecommendedService, SignalType, UrgencyLevel
from app.domain.models import TenantSignalPreference
from app.domain.types import LlmOutput

logger = get_logger(__name__)

# Cost controls. The crawler caps raw content at 20,000 chars; we
# truncate further here because the LLM bill scales with input tokens
# and the lead almost always sits in the lede.
MAX_INPUT_CHARS = 12_000
HEAD_KEEP = MAX_INPUT_CHARS - 500
TAIL_KEEP = 500

# Items shorter than this are too thin to classify reliably and burn
# tokens for no payoff — caught by the verifier as a hard gate so a
# misconfigured collector cannot run up the LLM bill.
MIN_USEFUL_CONTENT_CHARS = 50

# Deterministic classification. Temperature > 0 would let the same
# article flip between signal / no-signal on retry, which breaks
# downstream dedupe and review workflows.
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 800   # JSON response is ~500 tokens with the new schema

MAX_PARSE_RETRIES = 1
RETRY_BACKOFF_SECONDS = 0.5

_VALID_SIGNAL_TYPES: frozenset[str] = frozenset(t.value for t in SignalType)
_VALID_URGENCY: frozenset[str] = frozenset(u.value for u in UrgencyLevel)
_VALID_SERVICES: frozenset[str] = frozenset(s.value for s in RecommendedService)


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

    @property
    def disabled(self) -> bool:
        return self._disabled

    def verify(
        self,
        *,
        source_type: str,
        title: str | None,
        url: str | None,
        content: str,
        preferences: TenantSignalPreference | None = None,
    ) -> LlmOutput:
        if self._disabled:
            return LlmOutput(prompt_version=CURRENT_VERSION)

        # Pre-LLM hard gates. Each one short-circuits without spending
        # tokens. They guard against three failure modes: empty / very
        # short content, missing both title and content (collector bug),
        # and pathological inputs where normalization would yield ''.
        if title is None and not (content and content.strip()):
            logger.debug("LLM skipped: no title and no content")
            return LlmOutput(prompt_version=CURRENT_VERSION)
        clean_content = (content or "").strip()
        if len(clean_content) < MIN_USEFUL_CONTENT_CHARS:
            logger.debug(
                "LLM skipped: content too short (%d chars)", len(clean_content)
            )
            return LlmOutput(prompt_version=CURRENT_VERSION)

        truncated = _truncate(clean_content, self._max_input_chars)
        user_prompt = build_user_prompt_v2(
            source_type=source_type,
            title=title,
            url=url,
            content=truncated,
            preferences=preferences,
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
                    system=SYSTEM_PROMPT_V2,
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
                # Transport / rate-limit. The SDK already retries 5xx;
                # anything reaching here is worth giving up on.
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
        '{"is_signal": false, "signal_type": null, "confidence": 0, '
        '"recommended_services": []}.'
    )


def _coerce_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_enum(value: object, allowed: frozenset[str]) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if text in allowed else None


def _coerce_service_list(value: object) -> list[str]:
    """recommended_services constrained to the controlled vocabulary.
    Out-of-vocab entries are dropped silently — no hallucinated services."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip().lower()
        if normalized in _VALID_SERVICES and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _map_to_llm_output(payload: dict) -> LlmOutput:
    """Turn the parsed JSON into a permissive LlmOutput.

    Invalid values do NOT raise — they collapse to sensible nulls. The
    downstream normalizer in signal_detector still has to validate, but
    by the time it runs the shape is already predictable.
    """
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

    is_signal_raw = payload.get("is_signal")
    is_signal = bool(is_signal_raw) if is_signal_raw is not None else (
        signal_type is not None
    )

    extracted = {
        "company_name": _coerce_str(payload.get("company_name")),
        "target_customer_type": _coerce_str(payload.get("target_customer_type")),
        "sector": _coerce_str(payload.get("sector")),
        "region": _coerce_str(payload.get("region")),
        "detected_event": _coerce_str(payload.get("detected_event")),
        "why_relevant_for_logistics": _coerce_str(
            payload.get("why_relevant_for_logistics")
        ),
        "potential_logistics_need": _coerce_str(
            payload.get("potential_logistics_need")
        ),
        "recommended_services": _coerce_service_list(
            payload.get("recommended_services")
        ),
        "urgency": _coerce_enum(payload.get("urgency"), _VALID_URGENCY),
        "suggested_sales_action": _coerce_str(payload.get("suggested_sales_action")),
        "suggested_outreach_message": _coerce_str(
            payload.get("suggested_outreach_message")
        ),
        "evidence_snippet": _coerce_str(payload.get("evidence_snippet")),
    }

    return LlmOutput(
        prompt_version=CURRENT_VERSION,
        is_signal=is_signal,
        signal_type=signal_type,
        confidence=confidence,
        extracted_fields=extracted,
    )
