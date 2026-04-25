"""Normalize raw scraper output into a stable shape.

Two kinds of normalization live here:
  - text: collapse whitespace, strip, hard-cap length so a runaway page
    cannot blow up the LLM prompt or the DB column.
  - urls: resolve relative links against the source page and drop
    tracking params so the same article under different UTM tags does
    not defeat the content_hash dedupe downstream.

Deeper semantic normalization (lowercasing, punctuation stripping) is
intentionally NOT done here — that belongs in app.core.hashing, which is
the single source of truth for the fields that end up in a hash.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

_WHITESPACE_RE = re.compile(r"\s+")
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
    }
)

MAX_CONTENT_CHARS = 20_000  # matches what we are willing to send to the LLM


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    collapsed = _WHITESPACE_RE.sub(" ", text).strip()
    return collapsed[:MAX_CONTENT_CHARS]


def clean_title(text: str | None) -> str | None:
    cleaned = clean_text(text)
    return cleaned or None


def absolutize(base_url: str, href: str | None) -> str | None:
    """Resolve `href` against `base_url` and strip tracking params."""
    if not href:
        return None
    absolute = urljoin(base_url, href.strip())
    return strip_tracking(absolute)


def strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        pair
        for pair in parts.query.split("&")
        if pair and pair.split("=", 1)[0] not in _TRACKING_PARAMS
    ]
    return urlunsplit(parts._replace(query="&".join(kept)))
