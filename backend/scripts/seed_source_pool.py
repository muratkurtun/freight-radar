"""Seed the platform source pool from a JSON manifest.

This script is meant to be run by the *platform admin*, not by tenants.
Tenants do not manage source URLs — the source pool is curated
centrally and tenants just pick taxonomies (see /tenant/preferences).

Usage (inside the backend container, where PYTHONPATH is set):

    cd /app
    python scripts/seed_source_pool.py \\
        --file seed/source_pool.example.json --dry-run
    python scripts/seed_source_pool.py \\
        --file seed/source_pool.production.json --update-existing

Behaviour
---------
* Reads a JSON array. Each entry is one platform source.
* Validates every record up front. Invalid entries default to
  fail-fast; pass --skip-invalid to drop them and continue.
* Idempotency match key: case-insensitive, trailing-slash-trimmed URL.
  - if no match → INSERT
  - if match    → SKIP by default; UPDATE only with --update-existing
* --dry-run runs the same code path but rolls the transaction back at
  the end and reports what would have happened.

Backend field mapping
---------------------
The script writes to the `sources` table with `tenant_id IS NULL`
(platform pool — see migration 0004). Field shapes match the ORM:

  name                 str
  source_type          one of {SourceType enum}
  url                  http/https
  is_active            bool (default true)
  region_tags          list[str], non-empty
  sector_tags          list[str], non-empty
  customer_type_tags   list[str], non-empty
  signal_focus_tags    list[str], non-empty
  language             str | null (max 10 chars)
  priority             int (default 100; lower runs first)
  quality_score        Decimal in [0.00, 1.00], optional
  noise_level          Decimal in [0.00, 1.00], optional
  config               dict (default {})

Note: the backend stores `quality_score` and `noise_level` as
Numeric(3,2) with range 0–1. If you have a 0–100 source list, divide
by 100 before seeding. The script enforces 0–1 strictly.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.enums import SourceType
from app.domain.models import Source

_VALID_SOURCE_TYPES = frozenset(t.value for t in SourceType)
_REQUIRED_TAG_FIELDS = (
    "region_tags",
    "sector_tags",
    "customer_type_tags",
    "signal_focus_tags",
)


def _normalize_url(url: str) -> str:
    """Match key for idempotency. Lowercase + strip trailing slash —
    enough to dedupe the common "https://Foo.com/feed" vs
    "https://foo.com/feed/" pair without trying to be clever about
    query strings (some RSS feeds carry meaningful ?format=rss params)."""
    return url.strip().rstrip("/").lower()


def _validate(record: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append("name is required")

    source_type = record.get("source_type")
    if source_type not in _VALID_SOURCE_TYPES:
        issues.append(
            f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}"
        )

    url = record.get("url")
    if not isinstance(url, str) or not url.strip():
        issues.append("url is required")
    elif not (url.startswith("http://") or url.startswith("https://")):
        issues.append("url must start with http:// or https://")

    for tag_field in _REQUIRED_TAG_FIELDS:
        value = record.get(tag_field)
        if not isinstance(value, list) or len(value) == 0:
            issues.append(f"{tag_field} must be a non-empty list of strings")
            continue
        if not all(isinstance(t, str) and t.strip() for t in value):
            issues.append(f"{tag_field} entries must be non-empty strings")

    is_active = record.get("is_active", True)
    if not isinstance(is_active, bool):
        issues.append("is_active must be a boolean")

    priority = record.get("priority", 100)
    if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
        issues.append("priority must be a non-negative integer")

    language = record.get("language")
    if language is not None and (not isinstance(language, str) or len(language) > 10):
        issues.append("language must be a string of 10 chars or less")

    for fld in ("quality_score", "noise_level"):
        value = record.get(fld)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(
                f"{fld} must be a number between 0 and 1 "
                f"(backend stores Numeric(3,2)); got {type(value).__name__}"
            )
            continue
        if not (0 <= float(value) <= 1):
            issues.append(
                f"{fld} must be between 0 and 1 (backend stores Numeric(3,2))"
            )

    config = record.get("config", {})
    if not isinstance(config, dict):
        issues.append("config must be an object if provided")

    return issues


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _find_existing(
    db: Session, normalized_url: str
) -> Source | None:
    """Look up a platform source by normalized URL.

    The platform pool is small (target 20–50 rows) so a full scan in
    Python is fine and keeps the case-insensitive match logic exactly
    in step with `_normalize_url`. The DB-level UNIQUE on
    `url WHERE tenant_id IS NULL` is the authoritative dedupe."""
    stmt = select(Source).where(Source.tenant_id.is_(None))
    for source in db.execute(stmt).scalars():
        if _normalize_url(source.url) == normalized_url:
            return source
    return None


def _apply(
    db: Session,
    record: dict[str, Any],
    *,
    update_existing: bool,
) -> str:
    """Insert / update / skip one record. Returns one of
    {'created','updated','skipped'}."""
    normalized_url = _normalize_url(record["url"])
    existing = _find_existing(db, normalized_url)

    payload = dict(
        source_type=record["source_type"],
        name=record["name"].strip(),
        url=record["url"].strip(),
        is_active=record.get("is_active", True),
        region_tags=list(record["region_tags"]),
        sector_tags=list(record["sector_tags"]),
        customer_type_tags=list(record["customer_type_tags"]),
        signal_focus_tags=list(record["signal_focus_tags"]),
        language=record.get("language"),
        priority=record.get("priority", 100),
        quality_score=_to_decimal(record.get("quality_score")),
        noise_level=_to_decimal(record.get("noise_level")),
        config=record.get("config", {}),
    )

    if existing is None:
        source = Source(tenant_id=None, **payload)
        db.add(source)
        db.flush()
        return "created"

    if not update_existing:
        return "skipped"

    for field, value in payload.items():
        setattr(existing, field, value)
    db.flush()
    return "updated"


def _print_summary(counts: dict[str, int], *, dry_run: bool) -> None:
    prefix = "[dry-run] " if dry_run else ""
    summary = (
        f"{prefix}created={counts['created']} updated={counts['updated']} "
        f"skipped={counts['skipped']} invalid={counts['invalid']}"
    )
    print(summary)


def run(
    *,
    path: str,
    dry_run: bool,
    update_existing: bool,
    skip_invalid: bool,
    session_factory=SessionLocal,
    stderr=sys.stderr,
) -> int:
    """Library-level entry point. Returns the exit code so tests can
    drive the script without spawning subprocesses."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(
            "seed file must be a JSON array of source objects",
            file=stderr,
        )
        return 2

    valid: list[dict[str, Any]] = []
    invalid: list[tuple[int, str, list[str]]] = []
    for idx, record in enumerate(data):
        if not isinstance(record, dict):
            invalid.append((idx, "<not-a-dict>", ["record must be an object"]))
            continue
        issues = _validate(record)
        if issues:
            invalid.append((idx, str(record.get("name", "<unnamed>")), issues))
            continue
        valid.append(record)

    if invalid:
        print("Validation failures:", file=stderr)
        for idx, name, issues in invalid:
            print(f"  [{idx}] {name}: {'; '.join(issues)}", file=stderr)
        if not skip_invalid:
            print(
                "Aborting. Pass --skip-invalid to drop bad rows and continue.",
                file=stderr,
            )
            return 2

    counts = {"created": 0, "updated": 0, "skipped": 0, "invalid": len(invalid)}
    with session_factory() as db:
        try:
            for record in valid:
                result = _apply(db, record, update_existing=update_existing)
                counts[result] += 1
        except Exception:
            db.rollback()
            raise
        if dry_run:
            db.rollback()
        else:
            db.commit()

    _print_summary(counts, dry_run=dry_run)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the platform source pool from a JSON manifest.",
    )
    parser.add_argument("--file", required=True, help="Path to JSON manifest.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + simulate; rolls back the transaction at the end.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="UPDATE rows whose URL matches; default is SKIP.",
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Drop invalid rows and continue. Default is fail-fast.",
    )
    args = parser.parse_args()

    rc = run(
        path=args.file,
        dry_run=args.dry_run,
        update_existing=args.update_existing,
        skip_invalid=args.skip_invalid,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
