"""Deterministic hashes used for dedupe at the DB layer.

Both content_hash (raw_source_items) and signal_hash (detected_signals) are
SHA-256 hex strings produced here so the normalization rules live in one
place. Changes to these rules effectively change the dedupe scope, so they
are kept narrow and explicit.
"""
import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text).strip().lower()


def content_hash(*, title: str | None, content: str) -> str:
    payload = f"{_normalize(title)}\n{_normalize(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signal_hash(
    *,
    signal_type: str,
    company_name: str | None,
    location: str | None,
    role_title: str | None,
    supplier_name: str | None,
) -> str:
    parts = [
        signal_type,
        _normalize(company_name),
        _normalize(location),
        _normalize(role_title),
        _normalize(supplier_name),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
