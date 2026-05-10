"""Tests for the platform source-pool seed script.

The script is executed by the platform admin, not by tenants. Tests
cover validation, idempotency (URL-normalized match), update-vs-skip
semantics, and dry-run isolation. The DB is faked because the seed
operation is a small library-level loop — exercising the full
SQLAlchemy stack would only retest the ORM.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import seed_source_pool


# --------------------------------------------------------------------------
# Fake Session
# --------------------------------------------------------------------------


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _FakeScalarsResult(self._rows)


class _FakeSession:
    """Captures inserts / updates so tests can inspect them."""

    def __init__(self, existing_sources: list | None = None):
        self.existing_sources = list(existing_sources or [])
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.flush_count = 0

    def execute(self, _stmt):
        return _FakeExecuteResult(self.existing_sources)

    def add(self, instance):
        self.added.append(instance)
        # mimic the FK-less pre-flush state — the script uses .flush()
        # to surface IntegrityErrors early but the fake just records.
        if instance.id is None:
            instance.id = uuid4()

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _session_factory(session: _FakeSession):
    """Factory that always returns the same session — lets a test
    seed initial state and inspect post-run state in one place."""
    yield session


def _factory_for(session: _FakeSession):
    def factory():
        return _session_factory(session)
    return factory


# --------------------------------------------------------------------------
# _normalize_url + _validate
# --------------------------------------------------------------------------


def test_normalize_url_lowercases_and_strips_trailing_slash():
    assert (
        seed_source_pool._normalize_url("HTTPS://Example.com/Feed/")
        == "https://example.com/feed"
    )


def test_validate_accepts_full_record():
    record = {
        "name": "x",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
        "language": "en",
        "priority": 100,
        "quality_score": 0.8,
        "noise_level": 0.2,
    }
    assert seed_source_pool._validate(record) == []


def test_validate_rejects_missing_required():
    record = {"source_type": "news"}
    issues = seed_source_pool._validate(record)
    # name + url + four tag fields all complain
    assert any("name is required" in i for i in issues)
    assert any("url is required" in i for i in issues)
    for tag_field in (
        "region_tags",
        "sector_tags",
        "customer_type_tags",
        "signal_focus_tags",
    ):
        assert any(tag_field in i for i in issues)


def test_validate_rejects_non_http_url():
    record = {
        "name": "x",
        "source_type": "news",
        "url": "ftp://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
    }
    issues = seed_source_pool._validate(record)
    assert any("http" in i for i in issues)


def test_validate_rejects_unknown_source_type():
    record = {
        "name": "x",
        "source_type": "not_a_real_type",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
    }
    issues = seed_source_pool._validate(record)
    assert any("source_type" in i for i in issues)


def test_validate_accepts_news_html_source_type():
    """Phase 12.5 added news_html to SourceType. The validator's
    `_VALID_SOURCE_TYPES` is built from the enum at import time so the
    new value flows through automatically — this test locks that
    contract in case someone hardcodes the set later."""
    record = {
        "name": "x",
        "source_type": "news_html",
        "url": "https://example.com/category/exports",
        "region_tags": ["turkey"],
        "sector_tags": ["industrial"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
    }
    assert seed_source_pool._validate(record) == []


def test_validate_accepts_all_source_types_in_enum():
    """Sanity floor: every SourceType enum value must round-trip
    through the seed validator. If a future enum value lands without
    the validator being aware, this test fires — the seed bill of
    materials must stay in sync with the read path."""
    from app.domain.enums import SourceType

    base = {
        "name": "x",
        "url": "https://example.com/path",
        "region_tags": ["turkey"],
        "sector_tags": ["industrial"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
    }
    for st in SourceType:
        record = {**base, "source_type": st.value}
        assert seed_source_pool._validate(record) == [], (
            f"validator rejected SourceType.{st.name} = {st.value!r}"
        )


def test_validate_rejects_empty_tag_arrays():
    record = {
        "name": "x",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": [],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
    }
    issues = seed_source_pool._validate(record)
    assert any("region_tags" in i for i in issues)


def test_validate_rejects_quality_score_out_of_range():
    """Backend stores Numeric(3,2). 0–100 inputs must be rescaled
    before seeding; the script enforces 0–1 strictly."""
    record = {
        "name": "x",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
        "quality_score": 75,
    }
    issues = seed_source_pool._validate(record)
    assert any("quality_score" in i for i in issues)


def test_validate_rejects_noise_level_out_of_range():
    record = {
        "name": "x",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
        "noise_level": 1.4,
    }
    issues = seed_source_pool._validate(record)
    assert any("noise_level" in i for i in issues)


def test_validate_rejects_negative_priority():
    record = {
        "name": "x",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
        "priority": -1,
    }
    issues = seed_source_pool._validate(record)
    assert any("priority" in i for i in issues)


# --------------------------------------------------------------------------
# run() — end-to-end through the fake Session
# --------------------------------------------------------------------------


def _valid_record(**overrides):
    base = {
        "name": "Sample Feed",
        "source_type": "news",
        "url": "https://example.com/feed",
        "region_tags": ["eu"],
        "sector_tags": ["logistics"],
        "customer_type_tags": ["exporter"],
        "signal_focus_tags": ["export_expansion"],
        "language": "en",
        "priority": 100,
        "quality_score": 0.8,
        "noise_level": 0.2,
        "config": {},
    }
    base.update(overrides)
    return base


def _write_seed(tmp_path: Path, records: list) -> str:
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(records), encoding="utf-8")
    return str(p)


def test_run_creates_new_source(tmp_path):
    """Empty pool + one valid record → one INSERT, commit, count=1."""
    session = _FakeSession(existing_sources=[])
    seed_path = _write_seed(tmp_path, [_valid_record()])

    rc = seed_source_pool.run(
        path=seed_path,
        dry_run=False,
        update_existing=False,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc == 0
    assert len(session.added) == 1
    inserted = session.added[0]
    assert inserted.tenant_id is None  # platform pool
    assert inserted.url == "https://example.com/feed"
    assert inserted.region_tags == ["eu"]
    assert inserted.quality_score == Decimal("0.8")
    assert session.committed is True
    assert session.rolled_back is False


def test_run_skips_duplicate_url_by_default(tmp_path):
    """Existing pool row with the same URL → no INSERT, count=skipped."""
    existing = SimpleNamespace(
        id=uuid4(),
        tenant_id=None,
        url="https://EXAMPLE.com/Feed/",  # case + slash differ → still match
        name="old",
        source_type="news",
    )
    session = _FakeSession(existing_sources=[existing])
    seed_path = _write_seed(tmp_path, [_valid_record()])

    rc = seed_source_pool.run(
        path=seed_path,
        dry_run=False,
        update_existing=False,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc == 0
    assert session.added == []
    # An UPDATE still wouldn't show up in `added`; verify by checking
    # the existing row was NOT mutated.
    assert existing.name == "old"


def test_run_updates_when_flag_set(tmp_path):
    """Same URL + --update-existing → existing row gets new fields."""
    existing = SimpleNamespace(
        id=uuid4(),
        tenant_id=None,
        url="https://example.com/feed",
        name="old name",
        source_type="news",
        is_active=False,
        region_tags=[],
        sector_tags=[],
        customer_type_tags=[],
        signal_focus_tags=[],
        language=None,
        priority=999,
        quality_score=None,
        noise_level=None,
        config={},
    )
    session = _FakeSession(existing_sources=[existing])
    seed_path = _write_seed(tmp_path, [_valid_record(name="new name")])

    rc = seed_source_pool.run(
        path=seed_path,
        dry_run=False,
        update_existing=True,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc == 0
    assert session.added == []
    assert existing.name == "new name"
    assert existing.region_tags == ["eu"]
    assert existing.priority == 100
    assert existing.quality_score == Decimal("0.8")
    assert session.committed is True


def test_dry_run_does_not_commit(tmp_path):
    session = _FakeSession(existing_sources=[])
    seed_path = _write_seed(tmp_path, [_valid_record()])

    rc = seed_source_pool.run(
        path=seed_path,
        dry_run=True,
        update_existing=False,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc == 0
    # The script still calls add() so it can inspect the would-be row,
    # but it MUST roll back instead of commit.
    assert session.committed is False
    assert session.rolled_back is True


def test_run_fails_fast_on_invalid_unless_skip(tmp_path):
    invalid = {"name": "broken"}  # missing url, source_type, tags, …
    session = _FakeSession(existing_sources=[])
    seed_path = _write_seed(tmp_path, [invalid, _valid_record()])

    rc_default = seed_source_pool.run(
        path=seed_path,
        dry_run=False,
        update_existing=False,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc_default == 2
    # No DB writes when we abort.
    assert session.added == []
    assert session.committed is False


def test_run_skip_invalid_continues(tmp_path):
    invalid = {"name": "broken"}
    session = _FakeSession(existing_sources=[])
    seed_path = _write_seed(tmp_path, [invalid, _valid_record()])

    rc = seed_source_pool.run(
        path=seed_path,
        dry_run=False,
        update_existing=False,
        skip_invalid=True,
        session_factory=_factory_for(session),
    )

    assert rc == 0
    assert len(session.added) == 1
    assert session.committed is True


def test_run_rejects_non_array_payload(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"not": "an array"}), encoding="utf-8")
    session = _FakeSession()

    rc = seed_source_pool.run(
        path=str(p),
        dry_run=False,
        update_existing=False,
        skip_invalid=False,
        session_factory=_factory_for(session),
    )

    assert rc == 2
    assert session.added == []


def test_example_seed_file_is_valid(tmp_path):
    """The shipped example must validate so a fresh `--dry-run` works
    out of the box. Records are inactive (`is_active=false`) on
    purpose so even an accidental non-dry-run is safe."""
    repo_root = Path(__file__).resolve().parent.parent
    example_path = repo_root / "seed" / "source_pool.example.json"
    with example_path.open(encoding="utf-8") as f:
        records = json.load(f)
    assert isinstance(records, list)
    for idx, record in enumerate(records):
        issues = seed_source_pool._validate(record)
        assert issues == [], f"example record #{idx} invalid: {issues}"
        assert record.get("is_active") is False, (
            f"example record #{idx} should ship inactive — "
            "demo URLs do not return real feed data"
        )
