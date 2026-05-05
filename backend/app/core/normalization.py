"""Deterministic text normalization for entity matching.

This module is the single source of truth for `normalized_name`-style
keys used by tenant-scoped uniqueness constraints (currently
`companies.normalized_name`). The same helper runs in:

  - the Pydantic / service layer when a signal mentions a company
  - the Alembic backfill in 0007_company_lead_view

so that the in-Python value and the migrated value land on the same
string. If you change these rules, bump a migration and rebackfill.
"""
from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s&]+", re.UNICODE)

# Suffixes we strip from the *end* of the normalized name. Strictly
# whitelisted — common Turkish & global corporate forms only — to keep
# the rule deterministic and avoid mis-collapsing legitimate distinct
# brands (e.g. "Acme Coffee" vs "Acme Café"). No fuzzy matching here
# by design; that's a later phase.
_COMPANY_SUFFIXES: tuple[str, ...] = (
    "anonim sirketi", "limited sirketi", "as", "ltd sti", "sti",
    "ltd", "limited", "inc", "incorporated", "corp", "corporation",
    "co", "company", "llc", "plc", "gmbh", "sa", "spa", "bv",
)

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


def normalize_company_name(value: str | None) -> str:
    """Return a canonical key for a company name.

    Steps (all deterministic, no fuzzy):
      1. Drop None / empty / whitespace-only → "" (caller decides skip)
      2. Turkish-fold + NFKD + strip combining marks → ASCII-ish
      3. Lowercase, collapse internal whitespace
      4. Remove punctuation except '&' (kept because "P&G" vs "PG" is
         a meaningful distinction in business names)
      5. Strip a single trailing legal-form suffix from the whitelist

    The empty string is returned (not a sentinel value) so callers can
    use the simple guard `if not normalized: skip`. The caller MUST
    treat `""` as "do not create a company row".
    """
    if not value:
        return ""
    folded = value.translate(_TR_FOLD)
    nfkd = unicodedata.normalize("NFKD", folded)
    ascii_like = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    text = _WS.sub(" ", ascii_like).strip().lower()
    if not text:
        return ""
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    if not text:
        return ""

    # Strip ONE trailing suffix at most. Iterating once is enough — we
    # don't want "ltd ltd" to fully collapse to "" and silently merge
    # unrelated companies.
    for suffix in _COMPANY_SUFFIXES:
        if text.endswith(" " + suffix):
            text = text[: -(len(suffix) + 1)].strip()
            break

    return text
