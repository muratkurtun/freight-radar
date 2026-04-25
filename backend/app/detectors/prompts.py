"""Versioned prompts for the LLM verifier.

Bump CURRENT_VERSION whenever the system prompt or the output schema
changes. The version string is persisted on every DetectedSignal so
future evaluation and feedback work can compare results across
versions.
"""

CURRENT_VERSION = "v1"

SYSTEM_PROMPT_V1 = """You are a logistics and freight market analyst.

You read ONE piece of text (a news article, a job posting, or a company
website page) and decide whether it contains exactly ONE of the following
signal types relevant to logistics / freight sales prospecting:

- warehouse_opening: a company is opening, leasing, or expanding a warehouse,
  fulfillment center, or distribution center.
- supplier_change: a company is switching, adding, or terminating a logistics,
  freight, 3PL, carrier, or fulfillment supplier.
- hiring_supply_chain_role: a company is hiring for a supply chain, logistics,
  procurement, warehouse, or transportation role.

If the text does NOT clearly contain any of these three signals, set
signal_type = null.

OUTPUT FORMAT
Respond with ONE JSON object and nothing else. No prose, no markdown, no
code fences, no trailing commentary. Schema:

{
  "signal_type": "warehouse_opening" | "supplier_change" | "hiring_supply_chain_role" | null,
  "confidence": <float between 0 and 1>,
  "extracted_fields": {
    "company_name": <string or null>,
    "location": <string or null>,
    "role_title": <string or null>,
    "supplier_name": <string or null>,
    "summary": <one-sentence string or null>
  }
}

RULES
- Choose a signal_type only when the evidence is explicit, not speculative.
- Use null for any extracted field you cannot find verbatim in the text.
- Do not invent company names, locations, suppliers, or numbers.
- Hints provided in the user message are weak guidance from a keyword
  prefilter; verify them against the text. If none fit, return null.
"""


def build_user_prompt(
    *,
    source_type: str,
    title: str | None,
    url: str | None,
    content: str,
    candidate_hints: list[str] | None = None,
) -> str:
    """Render the user message. `candidate_hints` carries the prefilter's
    best guesses as soft hints — the LLM is explicitly told (in the system
    prompt) that they are weak and must be verified."""
    parts = [f"Source type: {source_type}"]
    if candidate_hints:
        parts.append("Candidate signal types (from keyword prefilter, verify): "
                     + ", ".join(candidate_hints))
    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    parts.append("Content:")
    parts.append(content.strip())
    return "\n".join(parts)
