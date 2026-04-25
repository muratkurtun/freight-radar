"""Orchestrator: raw item -> LlmOutput (via LlmVerifier) -> SignalResult.

This module does NOT call the LLM. It delegates that to LlmVerifier and
focuses on normalization: validating the signal_type, clamping and
quantizing the confidence, and splitting promoted columns out of the
extracted_fields dict so the result is ready for the DB layer.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.core.logging import get_logger
from app.detectors.llm_verifier import LlmVerifier
from app.detectors.prompts import CURRENT_VERSION
from app.domain.enums import SignalType
from app.domain.types import LlmOutput, SignalResult

logger = get_logger(__name__)

_VALID_TYPES: frozenset[str] = frozenset(t.value for t in SignalType)
_PROMOTED_FIELDS: tuple[str, ...] = (
    "company_name",
    "location",
    "role_title",
    "supplier_name",
    "summary",
)


class SignalDetector:
    def __init__(self, verifier: LlmVerifier | None = None):
        self._verifier = verifier or LlmVerifier()

    def detect(
        self,
        *,
        source_type: str,
        title: str | None,
        url: str | None,
        content: str,
        candidate_hints: Iterable[SignalType] | None = None,
    ) -> SignalResult:
        output = self._verifier.verify(
            source_type=source_type,
            title=title,
            url=url,
            content=content,
            candidate_hints=candidate_hints,
        )
        return _normalize(output)


def _normalize(out: LlmOutput) -> SignalResult:
    signal_type: SignalType | None = (
        SignalType(out.signal_type) if out.signal_type in _VALID_TYPES else None
    )

    clamped = max(0.0, min(1.0, out.confidence))
    confidence = Decimal(str(clamped)).quantize(Decimal("0.001"))

    promoted = {k: _clean_str(out.extracted_fields.get(k)) for k in _PROMOTED_FIELDS}
    extra = {k: v for k, v in out.extracted_fields.items() if k not in _PROMOTED_FIELDS}

    return SignalResult(
        prompt_version=out.prompt_version or CURRENT_VERSION,
        signal_type=signal_type,
        confidence=confidence,
        company_name=promoted["company_name"],
        location=promoted["location"],
        role_title=promoted["role_title"],
        supplier_name=promoted["supplier_name"],
        summary=promoted["summary"],
        extra=extra,
    )


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
