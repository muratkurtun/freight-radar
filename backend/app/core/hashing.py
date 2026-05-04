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
    region: str | None,
    target_customer_type: str | None,
) -> str:
    """Dedupe key for detected_signals.

    Migration 0005 changed the inputs from
        (type, company, location, role_title, supplier_name)
    to
        (type, company, region, target_customer_type)
    so that the same company surfacing the same lead in the same region
    + segment dedupes once. Different segments for the same company
    stay separate (e.g. ABC Foods as exporter and as distributor are
    two leads).

    The change is safe for existing rows: their hashes were computed
    over a different shape, so old vs new hashes never collide. Old
    rows therefore stay valid under the same UNIQUE(tenant_id, signal_hash)
    constraint."""
    parts = [
        signal_type,
        _normalize(company_name),
        _normalize(region),
        _normalize(target_customer_type),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
