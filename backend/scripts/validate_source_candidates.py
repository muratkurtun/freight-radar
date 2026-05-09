"""Automate the boring half of the Phase 12.1 source-validation checklist.

The platform admin's curation worksheet
(`docs/phase_12_1_first_production_source_pool_curation.md`) lists a
~12-step validation gate every source must pass before the operator
flips `is_active=true`. Several of those steps are mechanical and
error-prone when done by hand for 15+ candidate URLs:

    * HTTP reachable (follow redirects, accept 2xx / 3xx)
    * News feed parses with feedparser, returns ≥1 entry
    * Body is non-empty

This script automates exactly those steps. It does NOT decide
acceptance — the human-eye checks (lead-sentence company names,
noise level, paywall behaviour, tag accuracy) stay with the operator.

Read-only: no DB connection, no writes. Safe to run on a developer
laptop or a server with outbound HTTP.

Input  : a JSON array of `{name, source_type, url}` candidates.
Output : a Markdown table for pasting into the curation worksheet,
         OR a JSON dump for piping into another tool.

Usage:

    python scripts/validate_source_candidates.py \\
        --file seed/candidates.working.json --format md
    python scripts/validate_source_candidates.py \\
        --file seed/candidates.working.json --format json > out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

import feedparser
import requests

REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "OpportunityRadar-SeedValidator/1.0 (+platform admin)"

# Maximum body kept per source. Some news feeds ship multi-MB archives;
# we don't need more than the first ~200 KB to count entries and confirm
# a non-empty body.
MAX_BYTES = 200_000


@dataclass
class ValidationResult:
    name: str
    url: str
    source_type: str
    http_status: int | None
    reachable: bool
    feed_parsed: bool | None      # None = not a news source / not checked
    entry_count: int | None
    bytes_received: int | None
    error: str | None             # human-readable note for the matrix


def _fetch(url: str) -> tuple[int | None, bytes, str | None]:
    """Best-effort GET. Returns (status, body, error_message). Body is
    truncated to MAX_BYTES; status is None when the request itself
    fails (DNS / TLS / connection refused / timeout)."""
    try:
        with requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
            stream=True,
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            chunks: list[bytes] = []
            received = 0
            for chunk in resp.iter_content(chunk_size=16_384):
                if not chunk:
                    continue
                chunks.append(chunk)
                received += len(chunk)
                if received >= MAX_BYTES:
                    break
            body = b"".join(chunks)
            return resp.status_code, body, None
    except requests.RequestException as e:
        return None, b"", _short_error(e)


def _short_error(e: BaseException) -> str:
    """Single-line error string suitable for a Markdown table cell.
    Strips long stack-style detail so the matrix stays scannable."""
    msg = str(e).strip()
    # requests likes to wrap MaxRetry / SSLError in nested reprs that
    # blow past 200 chars; keep it terse.
    if len(msg) > 160:
        msg = msg[:157] + "…"
    return msg.replace("\n", " ")


def validate_candidate(record: dict) -> ValidationResult:
    name = str(record.get("name", "<unnamed>"))
    url = str(record.get("url", ""))
    source_type = str(record.get("source_type", ""))

    if not url or url.startswith("REPLACE"):
        return ValidationResult(
            name=name, url=url, source_type=source_type,
            http_status=None, reachable=False,
            feed_parsed=None, entry_count=None, bytes_received=None,
            error="placeholder url — replace before validating",
        )

    status, body, fetch_err = _fetch(url)
    if fetch_err is not None or status is None:
        return ValidationResult(
            name=name, url=url, source_type=source_type,
            http_status=None, reachable=False,
            feed_parsed=None, entry_count=None, bytes_received=None,
            error=fetch_err or "no http status",
        )

    reachable = 200 <= status < 400
    bytes_received = len(body)
    error = None if reachable else f"HTTP {status}"

    feed_parsed: bool | None = None
    entry_count: int | None = None

    if reachable and source_type == "news" and body:
        try:
            parsed = feedparser.parse(body)
            entries = list(getattr(parsed, "entries", []) or [])
            entry_count = len(entries)
            feed_parsed = entry_count > 0
            if not feed_parsed and getattr(parsed, "bozo", False):
                # Body fetched but didn't parse as a feed — highlight
                # so the operator looks at the URL again.
                error = error or "no feed entries (bozo)"
        except Exception as e:  # pragma: no cover — feedparser is robust
            feed_parsed = False
            entry_count = 0
            error = error or f"feedparser: {_short_error(e)}"

    return ValidationResult(
        name=name, url=url, source_type=source_type,
        http_status=status, reachable=reachable,
        feed_parsed=feed_parsed, entry_count=entry_count,
        bytes_received=bytes_received, error=error,
    )


def render_markdown(results: list[ValidationResult]) -> str:
    """Render a Markdown table the operator can paste straight into
    the curation worksheet's validation section."""
    lines = [
        "| Name | source_type | HTTP | Reachable | Feed | Entries | Bytes | Notes |",
        "|------|-------------|------|-----------|------|---------|-------|-------|",
    ]
    for r in results:
        feed_cell = "—" if r.feed_parsed is None else ("ok" if r.feed_parsed else "fail")
        entry_cell = "—" if r.entry_count is None else str(r.entry_count)
        bytes_cell = "—" if r.bytes_received is None else str(r.bytes_received)
        http_cell = "—" if r.http_status is None else str(r.http_status)
        notes = (r.error or "").replace("|", "\\|")
        reach = "✓" if r.reachable else "✗"
        lines.append(
            f"| {r.name} | {r.source_type} | {http_cell} | {reach} | "
            f"{feed_cell} | {entry_cell} | {bytes_cell} | {notes} |"
        )
    return "\n".join(lines)


def render_json(results: list[ValidationResult]) -> str:
    return json.dumps([asdict(r) for r in results], indent=2)


def run(
    *,
    path: str,
    fmt: str,
    stdout=sys.stdout,
    stderr=sys.stderr,
    validator=validate_candidate,
) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not read candidates: {e}", file=stderr)
        return 2
    if not isinstance(data, list):
        print("candidates file must be a JSON array", file=stderr)
        return 2

    results: list[ValidationResult] = []
    for record in data:
        if not isinstance(record, dict):
            results.append(
                ValidationResult(
                    name="<not-a-dict>", url="", source_type="",
                    http_status=None, reachable=False,
                    feed_parsed=None, entry_count=None, bytes_received=None,
                    error="record must be an object",
                )
            )
            continue
        results.append(validator(record))

    out = render_json(results) if fmt == "json" else render_markdown(results)
    print(out, file=stdout)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate candidate platform sources (HTTP + feed parse).",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="JSON array of {name, source_type, url} objects.",
    )
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format. md = Markdown table for the worksheet; "
        "json = machine-readable, suitable for piping.",
    )
    args = parser.parse_args()
    sys.exit(run(path=args.file, fmt=args.format))


if __name__ == "__main__":
    main()
