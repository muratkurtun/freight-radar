"""Coarse keyword gate that runs BEFORE the LLM.

Post-pivot the detector is a single broad recall-first filter, not a
per-type classifier. The LLM (constrained by tenant preferences) does
the real categorization; the gate's job is to keep clearly-irrelevant
items (sports, weather, lifestyle, opinion columns) from running up
the OpenAI bill.

Cost guardrails enforced here:
    * Empty / very short content                → False
    * Title and content both missing            → False
    * No business-relevance keyword in the text → False (NEWS only)
    * JOB_BOARD source                          → True (every posting
                                                  is potentially a
                                                  hiring signal)

The verifier has its own MIN_USEFUL_CONTENT_CHARS hard gate as
defense in depth. Both must agree before tokens are spent.

No DB, no tenant context, no LLM calls live in this module.
"""
from __future__ import annotations

import re
import unicodedata

from app.domain.enums import SourceType

# Items shorter than this are classified as too-thin without spending
# LLM tokens. Keep aligned with verifier MIN_USEFUL_CONTENT_CHARS — both
# must accept the item before the verifier calls the API.
MIN_GATE_CONTENT_CHARS = 50


# --------------------------------------------------------------------------
# Normalization (Turkish-aware)
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")

# NFKD alone does not decompose ş / ğ / ı cleanly, so translate them
# explicitly. Applied to BOTH the keyword set (at module load) and the
# haystack (at gate time).
_TR_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    }
)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    folded = text.translate(_TR_FOLD)
    nfkd = unicodedata.normalize("NFKD", folded)
    ascii_like = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return _WS.sub(" ", ascii_like).strip().lower()


# --------------------------------------------------------------------------
# Broad-gate keyword set
#
# Tuned for RECALL: a false positive costs one LLM call (which will then
# decide is_signal=False); a false negative drops the item forever. The
# set covers the surface phrases of every v2 SignalType plus the most
# common framings around expansion / hiring / investment / supply-chain
# pain. Authored in source language; normalized at module load so authors
# can write naturally with Turkish characters.
# --------------------------------------------------------------------------

_BUSINESS_KEYWORDS: tuple[str, ...] = (
    # Expansion / new operations
    "expand", "expansion", "expanding",
    "open", "opens", "opened", "opening",
    "launch", "launches", "launched",
    "inaugurate", "inaugurated", "inauguration",
    "ground breaking", "groundbreaking", "ribbon cutting",
    "new factory", "new plant", "new facility",
    "new warehouse", "new distribution center", "new fulfillment center",
    "new logistics center", "new logistics hub",
    "new production line",
    "new market", "new country", "enters market",

    # Capacity / investment
    "capacity increase", "increase capacity", "capacity expansion",
    "production capacity",
    "investment", "invests", "invested",
    "incentive", "subsidy",
    "funding round", "raised", "series a", "series b",

    # Trade / cross-border
    "export", "exports", "exporting", "exported",
    "import", "imports", "importing",
    "ihracat", "ithalat",
    "customs", "gumruk",

    # Hiring (broad — verifier disambiguates type)
    "hiring", "we are hiring", "join our team",
    "open position", "open positions", "job opening",
    "is ilani", "ise alim", "acik pozisyon",
    "logistics manager", "supply chain", "tedarik zinciri",
    "export manager", "import manager",
    "warehouse manager", "depo muduru",
    "freight forwarder", "forwarding",
    "customs broker",

    # Distribution / e-commerce
    "distributor", "distributorship", "dealership",
    "retail expansion", "store opening",
    "ecommerce", "e-commerce", "fulfillment", "fulfilment",
    "online store", "marketplace launch",

    # Tenders / contracts / deals
    "tender", "contract", "agreement", "deal",
    "awarded", "awards contract", "signs agreement",
    "ihale", "sozlesme", "anlasma",
    "partners with", "partnership with",

    # Supply chain pain
    "supply chain disruption", "shortage", "logistics problem",
    "shipping delay", "delivery delay",
    "tedarik sorunu",

    # Turkish equivalents for the most common positives so a TR-only
    # newsroom matches without an English keyword needing to leak in.
    "yeni depo", "yeni fabrika", "yeni tesis",
    "yeni dagitim merkezi", "yeni lojistik merkezi",
    "depo acilisi",
    "kapasite artisi",
    "yeni pazar", "yeni ulkeye",
    "bayilik", "distributorluk",
    "yatirim tesvigi", "tesvik belgesi",
)


def _compile(phrases: tuple[str, ...]) -> re.Pattern[str]:
    """One alternation with word boundaries so 'fleet' doesn't match
    'fleeting' and 'depo' doesn't match 'depolama'. Longest-first so
    overlapping phrases pick the most specific match deterministically."""
    seen: set[str] = set()
    patterns: list[str] = []
    for raw in phrases:
        norm = _normalize(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        patterns.append(rf"\b{re.escape(norm)}\b")
    patterns.sort(key=len, reverse=True)
    return re.compile("|".join(patterns))


_GATE_PATTERN = _compile(_BUSINESS_KEYWORDS)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def is_business_relevant(
    *,
    source_type: str,
    title: str | None,
    content: str,
) -> bool:
    """Coarse logistics-lead relevance gate.

    Returns True when an item is plausibly worth running through the LLM,
    False when it should be dropped without any LLM call.

    Job-board items always pass — every posting is a potential hiring
    signal and the role keyword set already lives in the verifier prompt.
    """
    if source_type == SourceType.JOB_BOARD.value:
        # Still require *some* content so a totally empty job posting
        # gets dropped here instead of failing in the verifier.
        return bool((content or "").strip()) or bool((title or "").strip())

    haystack = _normalize(f"{title or ''} {content or ''}")
    if len(haystack) < MIN_GATE_CONTENT_CHARS:
        return False
    return _GATE_PATTERN.search(haystack) is not None


def should_call_llm(
    *,
    source_type: str,
    title: str | None,
    content: str,
) -> bool:
    """Explicit gate the pipeline calls before spending LLM tokens.

    A thin alias over `is_business_relevant`. Keeping the named helper
    makes the call site readable: `if not should_call_llm(...): continue`.
    """
    return is_business_relevant(
        source_type=source_type, title=title, content=content
    )
