"""Rule-based candidate prefilter (runs BEFORE the LLM).

A cheap keyword / regex pass over the normalized title+content of a raw
item. It answers one question per item:

    "Is this worth spending LLM tokens on, and if so, for which
     signal types?"

Design principles
-----------------
* Tuned for recall, not precision. A false positive here costs one LLM
  call (the AI will then decide `is_signal=False`). A false negative
  drops the item forever, so we err on the side of letting things
  through.
* Negative rules are narrow. They only fire on phrases that very
  reliably mean the opposite of the candidate (e.g. "warehouse closes"
  rules out a `warehouse_opening` candidate).
* `hiring_supply_chain_role` uses AND logic: a hiring verb AND a
  supply-chain role keyword. On a JOB_BOARD source, hiring intent is
  implicit, so a role keyword alone is enough.

Integration
-----------
    from app.detectors.candidate_detector import detect_candidate_signals

    candidates = detect_candidate_signals(
        source_type=source.source_type,
        title=item.title,
        content=item.content,
    )
    if not candidates:
        # no plausible signal -> skip the LLM call entirely
        continue
    result = signal_detector.detect(...)   # only now pay for tokens

No DB, no tenant context, no AI calls live in this module.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

from app.domain.enums import SignalType, SourceType


@dataclass(slots=True, kw_only=True, frozen=True)
class Candidate:
    """One plausible SignalType for a raw item, with the phrases that matched.

    `score` is the number of distinct matched phrases (higher = stronger
    candidate). It is NOT a probability and must not leak into confidence
    on DetectedSignal — that's the LLM's job."""

    signal_type: SignalType
    score: int
    matched: tuple[str, ...]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")

# Turkish-specific fold map. NFKD alone does not decompose ş / ğ / ı
# cleanly, so we translate them explicitly. Applied to BOTH the keyword
# lists (at module load) and the haystack (at detect time), which means
# authors can write keywords naturally with Turkish characters and a
# news article that drops accents still matches.
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
# Keyword groups (authored in source language; normalized at compile time)
# --------------------------------------------------------------------------

_WAREHOUSE_OPENING_POS: tuple[str, ...] = (
    # EN — explicit new-facility phrases
    "new warehouse",
    "new distribution center", "new distribution centre",
    "new fulfillment center", "new fulfilment centre",
    "new logistics center", "new logistics centre",
    "new logistics hub",
    "opens warehouse", "opens a warehouse", "opens new warehouse",
    "opens distribution center", "opens distribution centre",
    "opens fulfillment center", "opens fulfilment centre",
    "opens logistics center", "opens logistics centre",
    "warehouse opening",
    "ground breaking", "groundbreaking",
    "ribbon cutting",
    "inaugurates warehouse", "inaugurates distribution center",
    "launches warehouse", "launches distribution center",
    "expands warehouse", "expanding warehouse",
    "adds warehouse capacity",
    # TR
    "yeni depo",
    "yeni lojistik merkezi",
    "yeni dagitim merkezi",
    "depo acilisi", "depo acilis",
    "lojistik merkezi acilisi",
    "dagitim merkezi acilisi",
)

_WAREHOUSE_OPENING_NEG: tuple[str, ...] = (
    "warehouse closes", "warehouse closed", "closing warehouse",
    "shuts warehouse", "warehouse shutdown",
    "warehouse layoff", "warehouse layoffs",
    "warehouse fire",
    "depo kapanisi", "depo kapandi",
)

_SUPPLIER_CHANGE_POS: tuple[str, ...] = (
    # EN
    "new supplier",
    "new logistics partner",
    "new logistics provider",
    "new 3pl",
    "selects logistics provider",
    "selects as supplier", "selected as supplier",
    "logistics partner",
    "partners with", "partnered with", "partnership with",
    "signs agreement", "signed agreement",
    "signs contract", "signed contract",
    "awarded contract", "awards contract",
    "supply agreement",
    "ends partnership", "terminates contract", "terminated contract",
    "switches supplier", "replaces supplier",
    "outsources logistics", "outsourcing agreement",
    # TR
    "yeni tedarikci",
    "tedarikci degisikligi",
    "yeni lojistik ortagi", "yeni lojistik partner",
    "anlasma imzaladi", "sozlesme imzaladi",
)

_SUPPLIER_CHANGE_NEG: tuple[str, ...] = (
    # These are PR events about suppliers, not actual supplier changes.
    "supplier conference", "supplier day", "supplier event", "supplier awards",
)

_HIRING_VERBS: tuple[str, ...] = (
    # Intent-to-hire signals. Only meaningful in AND with a role keyword.
    "hiring", "now hiring", "we are hiring", "were hiring", "we're hiring",
    "job opening", "job openings", "job vacancy",
    "open position", "open positions",
    "apply now", "join our team",
    # TR
    "is ilani", "ise alim", "acik pozisyon", "basvuru",
)

_SUPPLY_ROLES: tuple[str, ...] = (
    # EN
    "supply chain",
    "logistics manager", "logistics coordinator", "logistics specialist",
    "logistics analyst", "logistics director",
    "procurement", "sourcing manager",
    "warehouse manager", "warehouse supervisor",
    "warehouse operator", "warehouse associate",
    "fleet manager", "fleet operations",
    "freight", "freight forwarder", "forwarding",
    "transportation manager", "transport manager",
    "customs broker",
    "3pl manager",
    "demand planner", "distribution planner",
    # TR
    "tedarik zinciri",
    "lojistik uzmani", "lojistik sorumlusu", "lojistik muduru",
    "satin alma uzmani", "satin alma muduru",
    "depo sorumlusu", "depo muduru",
    "nakliye",
    "gumruk",
    "ithalat ihracat",
)


# --------------------------------------------------------------------------
# Compile
# --------------------------------------------------------------------------

def _compile(phrases: tuple[str, ...]) -> re.Pattern[str] | None:
    """Compile phrases into one alternation with word boundaries.

    Word boundaries (\\b) prevent "fleet" from matching "fleeting" and
    "depo" from matching "depolama". Longest-first ordering gives
    deterministic overlap behavior so `supply chain` wins over `supply`.
    """
    if not phrases:
        return None
    seen: set[str] = set()
    patterns: list[str] = []
    for raw in phrases:
        norm = _normalize(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        patterns.append(rf"\b{re.escape(norm)}\b")
    if not patterns:
        return None
    patterns.sort(key=len, reverse=True)
    return re.compile("|".join(patterns))


_WH_POS = _compile(_WAREHOUSE_OPENING_POS)
_WH_NEG = _compile(_WAREHOUSE_OPENING_NEG)
_SUP_POS = _compile(_SUPPLIER_CHANGE_POS)
_SUP_NEG = _compile(_SUPPLIER_CHANGE_NEG)
_HIRING_VERBS_PAT = _compile(_HIRING_VERBS)
_SUPPLY_ROLES_PAT = _compile(_SUPPLY_ROLES)


def _find_unique(pattern: re.Pattern[str] | None, haystack: str) -> tuple[str, ...]:
    if pattern is None:
        return ()
    seen: set[str] = set()
    matches: list[str] = []
    for m in pattern.finditer(haystack):
        text = m.group(0)
        if text in seen:
            continue
        seen.add(text)
        matches.append(text)
    return tuple(matches)


# --------------------------------------------------------------------------
# Per-type detection
# --------------------------------------------------------------------------

_Detector = Callable[[str, str], "Candidate | None"]


def _detect_warehouse_opening(text: str, source_type: str) -> Candidate | None:
    if _find_unique(_WH_NEG, text):
        return None
    positives = _find_unique(_WH_POS, text)
    if not positives:
        return None
    return Candidate(
        signal_type=SignalType.WAREHOUSE_OPENING,
        score=len(positives),
        matched=positives,
    )


def _detect_supplier_change(text: str, source_type: str) -> Candidate | None:
    if _find_unique(_SUP_NEG, text):
        return None
    positives = _find_unique(_SUP_POS, text)
    if not positives:
        return None
    return Candidate(
        signal_type=SignalType.SUPPLIER_CHANGE,
        score=len(positives),
        matched=positives,
    )


def _detect_hiring_supply_chain(text: str, source_type: str) -> Candidate | None:
    roles = _find_unique(_SUPPLY_ROLES_PAT, text)
    if not roles:
        return None
    # Job-board items are implicitly "we are hiring"; no verb required.
    if source_type == SourceType.JOB_BOARD.value:
        verbs: tuple[str, ...] = ()
    else:
        verbs = _find_unique(_HIRING_VERBS_PAT, text)
        if not verbs:
            return None
    return Candidate(
        signal_type=SignalType.HIRING_SUPPLY_CHAIN_ROLE,
        score=len(roles) + len(verbs),
        matched=roles + verbs,
    )


_DETECTORS: tuple[_Detector, ...] = (
    _detect_warehouse_opening,
    _detect_supplier_change,
    _detect_hiring_supply_chain,
)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def detect_candidate_signals(
    *,
    source_type: str,
    title: str | None,
    content: str,
) -> list[Candidate]:
    """Return zero or more Candidate hints for the item.

    Empty list   -> do NOT call the LLM (item is not a plausible signal).
    Non-empty    -> call the LLM; the hints may be passed to the prompt
                     as additional context.
    """
    haystack = _normalize(f"{title or ''} {content}")
    if not haystack:
        return []

    out: list[Candidate] = []
    for detector in _DETECTORS:
        c = detector(haystack, source_type)
        if c is not None:
            out.append(c)
    return out


def should_call_llm(candidates: list[Candidate]) -> bool:
    """Explicit gate the pipeline calls before spending LLM tokens."""
    return bool(candidates)
