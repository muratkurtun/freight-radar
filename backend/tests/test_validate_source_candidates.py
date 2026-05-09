"""Tests for the candidate-source validator helper.

Covers the categorisation logic (placeholder / unreachable / reachable
/ news-with-entries / news-without-entries) and the run() exit-code
contract. Network access is mocked at the requests + feedparser
boundaries so the suite stays hermetic.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import validate_source_candidates as v


# --------------------------------------------------------------------------
# validate_candidate — single-record categorisation
# --------------------------------------------------------------------------


def test_validate_skips_placeholder_url():
    """A row that still carries the seed-template `REPLACE_WITH_REAL_URL`
    placeholder MUST NOT issue an HTTP request — it would resolve and
    add 404 noise to the validator output. The validator short-
    circuits with a clear note instead."""
    with patch.object(v, "_fetch") as fetch:
        result = v.validate_candidate(
            {"name": "X", "source_type": "news", "url": "REPLACE_WITH_REAL_URL"}
        )
        fetch.assert_not_called()
    assert result.reachable is False
    assert result.http_status is None
    assert "placeholder" in (result.error or "")


def test_validate_unreachable_url_records_error():
    with patch.object(v, "_fetch", return_value=(None, b"", "DNS lookup failed")):
        result = v.validate_candidate(
            {"name": "X", "source_type": "news", "url": "https://nope.invalid/"}
        )
    assert result.reachable is False
    assert result.http_status is None
    assert result.error == "DNS lookup failed"
    assert result.feed_parsed is None  # we never tried to parse


def test_validate_news_feed_with_entries():
    body = b"<rss/>"  # parsed shape comes from the mock, not the body
    fake_parsed = SimpleNamespace(
        entries=[{"title": f"e{i}"} for i in range(3)], bozo=False
    )
    with patch.object(v, "_fetch", return_value=(200, body, None)), \
         patch.object(v.feedparser, "parse", return_value=fake_parsed):
        result = v.validate_candidate(
            {"name": "Vertical News", "source_type": "news",
             "url": "https://example.com/feed"}
        )
    assert result.reachable is True
    assert result.http_status == 200
    assert result.feed_parsed is True
    assert result.entry_count == 3
    assert result.error is None


def test_validate_news_feed_without_entries_flagged():
    """Empty feed (bozo=true or zero entries) surfaces in the notes
    column so the operator notices a likely template / homepage URL
    that isn't actually a feed."""
    fake_parsed = SimpleNamespace(entries=[], bozo=True)
    with patch.object(v, "_fetch", return_value=(200, b"<html/>", None)), \
         patch.object(v.feedparser, "parse", return_value=fake_parsed):
        result = v.validate_candidate(
            {"name": "X", "source_type": "news", "url": "https://example.com/"}
        )
    assert result.reachable is True
    assert result.feed_parsed is False
    assert result.entry_count == 0
    assert "no feed entries" in (result.error or "")


def test_validate_non_news_skips_feedparser():
    """job_board / company_website rows are validated for
    reachability only — the collector decides if its selectors apply,
    not the validator."""
    with patch.object(v, "_fetch", return_value=(200, b"<html/>", None)), \
         patch.object(v.feedparser, "parse") as parse:
        result = v.validate_candidate(
            {"name": "X", "source_type": "job_board",
             "url": "https://example.com/jobs"}
        )
        parse.assert_not_called()
    assert result.reachable is True
    assert result.feed_parsed is None
    assert result.entry_count is None


def test_validate_http_error_status_marked_unreachable():
    with patch.object(v, "_fetch", return_value=(404, b"", None)):
        result = v.validate_candidate(
            {"name": "X", "source_type": "news",
             "url": "https://example.com/missing"}
        )
    assert result.reachable is False
    assert result.http_status == 404
    assert result.error == "HTTP 404"


def test_validate_3xx_treated_as_reachable():
    """`requests` follows redirects by default, but a final 301/302
    after redirects-disabled would still be acceptable for the
    reachability check (operator may want to record the final URL
    later — this validator only reports the status)."""
    with patch.object(v, "_fetch", return_value=(301, b"", None)):
        result = v.validate_candidate(
            {"name": "X", "source_type": "news",
             "url": "https://example.com/old"}
        )
    assert result.reachable is True
    assert result.http_status == 301


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------


def test_render_markdown_includes_header_and_row():
    results = [
        v.ValidationResult(
            name="Vertical News", url="https://example.com/feed",
            source_type="news",
            http_status=200, reachable=True,
            feed_parsed=True, entry_count=12, bytes_received=4321,
            error=None,
        ),
    ]
    md = v.render_markdown(results)
    lines = md.splitlines()
    assert lines[0].startswith("| Name | source_type")
    assert "|------" in lines[1]
    assert "Vertical News" in lines[2]
    assert "200" in lines[2]
    assert "12" in lines[2]


def test_render_markdown_escapes_pipe_in_notes():
    """A `|` inside an error message would break Markdown table
    columns; the renderer escapes it."""
    results = [
        v.ValidationResult(
            name="X", url="https://example.com/", source_type="news",
            http_status=None, reachable=False,
            feed_parsed=None, entry_count=None, bytes_received=None,
            error="connection error: a | b",
        ),
    ]
    md = v.render_markdown(results)
    # The error cell should not introduce an unescaped `|`.
    error_row = md.splitlines()[2]
    # 9 columns → 10 separators; escaping keeps that count.
    assert error_row.count("|") == 10


def test_render_json_round_trips():
    results = [
        v.ValidationResult(
            name="X", url="u", source_type="news",
            http_status=200, reachable=True,
            feed_parsed=True, entry_count=1, bytes_received=10,
            error=None,
        ),
    ]
    out = v.render_json(results)
    parsed = json.loads(out)
    assert isinstance(parsed, list) and len(parsed) == 1
    assert parsed[0]["name"] == "X"
    assert parsed[0]["entry_count"] == 1


# --------------------------------------------------------------------------
# run() — file IO + exit codes
# --------------------------------------------------------------------------


def _write(tmp_path: Path, payload) -> str:
    p = tmp_path / "candidates.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_run_emits_markdown_for_valid_input(tmp_path):
    seed = [{"name": "X", "source_type": "news", "url": "https://example.com/"}]
    path = _write(tmp_path, seed)
    buf = io.StringIO()

    fake = v.ValidationResult(
        name="X", url="https://example.com/", source_type="news",
        http_status=200, reachable=True,
        feed_parsed=True, entry_count=5, bytes_received=100,
        error=None,
    )
    rc = v.run(path=path, fmt="md", stdout=buf, validator=lambda _r: fake)
    assert rc == 0
    out = buf.getvalue()
    assert "| Name | source_type" in out
    assert "X" in out


def test_run_emits_json_for_valid_input(tmp_path):
    seed = [{"name": "X", "source_type": "news", "url": "https://example.com/"}]
    path = _write(tmp_path, seed)
    buf = io.StringIO()

    fake = v.ValidationResult(
        name="X", url="https://example.com/", source_type="news",
        http_status=200, reachable=True,
        feed_parsed=True, entry_count=5, bytes_received=100,
        error=None,
    )
    rc = v.run(path=path, fmt="json", stdout=buf, validator=lambda _r: fake)
    assert rc == 0
    parsed = json.loads(buf.getvalue())
    assert parsed[0]["entry_count"] == 5


def test_run_rejects_non_array_payload(tmp_path):
    path = _write(tmp_path, {"not": "an array"})
    rc = v.run(path=path, fmt="md", stderr=io.StringIO(),
               validator=lambda _r: None)
    assert rc == 2


def test_run_handles_non_dict_records(tmp_path):
    """A stray scalar in the array must not crash; it gets reported
    as an invalid row."""
    path = _write(tmp_path, [{"name": "X", "source_type": "news",
                              "url": "https://example.com/"}, "stringy"])
    buf = io.StringIO()
    fake = v.ValidationResult(
        name="X", url="https://example.com/", source_type="news",
        http_status=200, reachable=True,
        feed_parsed=True, entry_count=1, bytes_received=1,
        error=None,
    )
    rc = v.run(path=path, fmt="md", stdout=buf, validator=lambda _r: fake)
    assert rc == 0
    out = buf.getvalue()
    assert "<not-a-dict>" in out
