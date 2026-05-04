"""Orchestrator: raw item -> LlmOutput (via LlmVerifier) -> SignalResult.

This module does NOT call the LLM. It delegates that to LlmVerifier and
focuses on:

  1. Validating the signal_type against the SignalType enum.
  2. Clamping and quantizing confidence to NUMERIC(4,3) shape.
  3. Promoting the v2 logistics-lead fields out of LlmOutput.extracted_fields
     into typed columns; anything the LLM returned outside the known
     schema goes to `extra` as JSONB.
  4. Enforcing the deterministic guardrails the verifier prompt cannot:
     - empty company_name → not a signal (sales cannot act on it)
     - the signal_type / confidence interplay is left as-is for review
"""
from __future__ import annotations

from decimal import Decimal

from app.core.logging import get_logger
from app.detectors.llm_verifier import LlmVerifier
from app.detectors.prompts import CURRENT_VERSION
from app.domain.enums import SignalType
from app.domain.models import TenantSignalPreference
from app.domain.types import LlmOutput, SignalResult

logger = get_logger(__name__)

_VALID_TYPES: frozenset[str] = frozenset(t.value for t in SignalType)

# v2 logistics-lead fields promoted out of LlmOutput.extracted_fields.
_PROMOTED_FIELDS: tuple[str, ...] = (
    "company_name",
    "target_customer_type",
    "sector",
    "region",
    "detected_event",
    "why_relevant_for_logistics",
    "potential_logistics_need",
    "urgency",
    "suggested_sales_action",
    "suggested_outreach_message",
    "evidence_snippet",
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
        preferences: TenantSignalPreference | None = None,
    ) -> SignalResult:
        output = self._verifier.verify(
            source_type=source_type,
            title=title,
            url=url,
            content=content,
            preferences=preferences,
        )
        return _normalize(output)


def _normalize(out: LlmOutput) -> SignalResult:
    signal_type: SignalType | None = (
        SignalType(out.signal_type) if out.signal_type in _VALID_TYPES else None
    )

    clamped = max(0.0, min(1.0, out.confidence))
    confidence = Decimal(str(clamped)).quantize(Decimal("0.001"))

    promoted = {k: _clean_str(out.extracted_fields.get(k)) for k in _PROMOTED_FIELDS}
    services_raw = out.extracted_fields.get("recommended_services")
    services = list(services_raw) if isinstance(services_raw, list) else []

    extra = {
        k: v
        for k, v in out.extracted_fields.items()
        if k not in _PROMOTED_FIELDS and k != "recommended_services"
    }

    # Deterministic guardrail: a signal must name a company. Sales cannot
    # act on "an unnamed Turkish exporter is expanding". The verifier
    # prompt asks for this too; this guard is the belt-and-suspenders.
    if signal_type is not None and not promoted["company_name"]:
        logger.debug(
            "Dropping signal: signal_type=%s but company_name empty",
            signal_type.value,
        )
        signal_type = None

    # Likewise, if the LLM's own is_signal is False, ignore any stray
    # signal_type it may have included — the LLM is the boolean
    # authority here.
    if not out.is_signal:
        signal_type = None

    return SignalResult(
        prompt_version=out.prompt_version or CURRENT_VERSION,
        signal_type=signal_type,
        confidence=confidence,
        company_name=promoted["company_name"],
        target_customer_type=promoted["target_customer_type"],
        sector=promoted["sector"],
        region=promoted["region"],
        detected_event=promoted["detected_event"],
        why_relevant_for_logistics=promoted["why_relevant_for_logistics"],
        potential_logistics_need=promoted["potential_logistics_need"],
        recommended_services=services,
        urgency=promoted["urgency"],
        suggested_sales_action=promoted["suggested_sales_action"],
        suggested_outreach_message=promoted["suggested_outreach_message"],
        evidence_snippet=promoted["evidence_snippet"],
        extra=extra,
    )


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
