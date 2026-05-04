"""Versioned prompts for the LLM verifier.

CURRENT_VERSION is persisted on every DetectedSignal; bump it whenever
the system prompt or the output schema changes so downstream evaluation
work can compare detector revisions side-by-side.

History
-------
- v1: pre-0005, three signal types (warehouse_opening, supplier_change,
  hiring_supply_chain_role). Output: company / location / role_title /
  supplier_name / summary.
- v2: post-0005 logistics sales lead detection. Thirteen signal types,
  controlled-vocab fields for customer/sector/region/services/urgency.
"""
from __future__ import annotations

from app.domain.enums import (
    RecommendedService,
    SignalType,
    UrgencyLevel,
)
from app.domain.models import TenantSignalPreference

CURRENT_VERSION = "v2"

_SIGNAL_TYPES = ", ".join(t.value for t in SignalType)
_SERVICES = ", ".join(s.value for s in RecommendedService)
_URGENCY = ", ".join(u.value for u in UrgencyLevel)


SYSTEM_PROMPT_V2 = f"""You are a logistics sales intelligence analyst.

Your task is to read ONE piece of text (a news article, a job posting,
or a company announcement) and decide whether it indicates a potential
logistics service need for freight forwarders, 3PLs, customs brokers,
or transportation companies.

PRODUCE A SIGNAL when the text indicates one of:
- A company expands exports or enters a new country / market
- A new factory, warehouse, fulfillment center or production line
- A clear capacity increase
- Hiring of export, import, logistics, or supply-chain roles
- A new distributorship or retail expansion
- E-commerce or fulfillment growth
- Supply chain disruption or operational logistics pain
- Investment incentives or public expansion announcements
- Tenders or contracts that imply logistics demand

DO NOT PRODUCE A SIGNAL when:
- No specific company is named
- The article is generic sector commentary
- A logistics company is announcing its own success (no customer lead)
- The connection to transportation / shipping is speculative
- The article is purely a financial result with no operational growth
- The signal would be off-target for this tenant's preferences (see
  the user message for the tenant's selected customer types, sectors,
  regions, and signal focuses — surface only signals that fit)

OUTPUT FORMAT
Respond with ONE JSON object and nothing else. No prose, no markdown,
no code fences. Schema:

{{
  "is_signal":          true | false,
  "signal_type":        one of [{_SIGNAL_TYPES}] or null,
  "confidence":         float between 0 and 1,
  "company_name":       string or null,
  "target_customer_type": string or null,
  "sector":             string or null,
  "region":             string or null,
  "detected_event":     short factual sentence or null,
  "why_relevant_for_logistics": short explanation or null,
  "potential_logistics_need": short explanation or null,
  "recommended_services": list of strings drawn from
                          [{_SERVICES}],
  "urgency":            one of [{_URGENCY}] or null,
  "suggested_sales_action": one short sentence or null,
  "suggested_outreach_message": one or two short sentences in the same
                                language as the source text, or null,
  "evidence_snippet":   verbatim quote from the input text that
                        supports the signal, or null
}}

RULES
- Set is_signal=false (and signal_type=null) when the criteria above
  are not met. Do not stretch a generic article into a signal.
- Use values present verbatim in the text; do not invent companies,
  countries, suppliers, sectors, or numbers.
- recommended_services MUST be a subset of the allowed list. Out-of-
  vocabulary values are dropped during normalization.
- evidence_snippet MUST be copied verbatim from the input.
- Confidence is your own calibration: 0.4 for weak inference, 0.7 for
  clearly stated, 0.9 only when the company explicitly states the need.
"""


def _format_taxonomy(label: str, values: list[str] | None) -> str | None:
    if not values:
        return None
    return f"{label}: " + ", ".join(values)


def build_user_prompt_v2(
    *,
    source_type: str,
    title: str | None,
    url: str | None,
    content: str,
    preferences: TenantSignalPreference | None = None,
) -> str:
    """Render the user message for v2.

    Tenant preferences are passed in as taxonomy lists so the LLM can
    skip signals that don't fit the tenant's profile (a Turkish 3PL
    targeting EU exporters does not need a Brazilian retail signal).
    """
    parts: list[str] = [f"Source type: {source_type}"]

    if preferences is not None:
        prefs_lines: list[str] = []
        prefs_lines.append(
            "TENANT TARGETING — produce signals only when the candidate "
            "matches AT LEAST ONE entry from each list the tenant selected. "
            "An empty list means the tenant did not constrain that dimension."
        )
        for label, values in (
            ("Target customer types", list(preferences.target_customer_types)),
            ("Sectors", list(preferences.sectors)),
            ("Regions", list(preferences.regions)),
            ("Signal focuses", list(preferences.signal_focuses)),
        ):
            line = _format_taxonomy(label, values)
            if line:
                prefs_lines.append("- " + line)
        parts.append("\n".join(prefs_lines))

    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    parts.append("Content:")
    parts.append(content.strip())
    return "\n".join(parts)


# Back-compat alias so callers can keep importing build_user_prompt.
# The signature is the v2 one; pre-pivot tests that pass
# `candidate_hints` use a thin shim provided in the verifier itself.
build_user_prompt = build_user_prompt_v2
