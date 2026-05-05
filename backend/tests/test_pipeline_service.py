"""Pipeline service tests.

The orchestrator pulls together a collector, a candidate prefilter, an
LLM verifier and four repositories. These tests bypass the real DB by
constructing PipelineService directly via __new__ and wiring in fakes
for every repo + the detector. The collector is registered through the
public registry so the source-type dispatch path is also exercised.

After migration 0004 sources are a platform-managed pool and tenants
pick preferences. The fakes here mirror that shape:
  - FakePlatformSourceRepo replaces the old tenant-scoped SourceRepo
  - FakePreferenceRepo carries the tenant's preference row
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Iterable
from uuid import UUID, uuid4

import pytest

from app.collectors import registry
from app.collectors.base import BaseCollector
from app.detectors.signal_detector import SignalDetector
from app.domain.enums import PipelineRunStatus, SignalType, SourceType
from app.domain.models import RawSourceItem
from app.domain.types import SignalResult, SourceItem
from app.services.pipeline_service import PipelineService


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeSession:
    """Just enough Session API for PipelineService."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.savepoints = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def merge(self, instance):
        return instance

    @contextmanager
    def begin_nested(self):
        self.savepoints += 1
        try:
            yield
        except Exception:
            raise


class FakePlatformSourceRepo:
    """Stub for PlatformSourceRepository. `match_for_preferences` mirrors
    the production semantics: empty prefs match nothing, inactive prefs
    short-circuit. `get` returns the configured source by id."""

    def __init__(self, sources):
        self._sources = list(sources)

    def get(self, source_id):
        for s in self._sources:
            if s.id == source_id:
                return s
        return None

    def get_or_404(self, source_id):
        s = self.get(source_id)
        if s is None:
            raise AssertionError(f"source {source_id} not in fake repo")
        return s

    def match_for_preferences(self, prefs):
        if prefs is None or not prefs.is_active:
            return []
        # Deterministic order: priority asc, id asc — matches repo SQL.
        return sorted(
            (s for s in self._sources if s.is_active),
            key=lambda s: (getattr(s, "priority", 100), str(s.id)),
        )


class FakePreferenceRepo:
    def __init__(self, pref=None):
        self._pref = pref

    def get(self):
        return self._pref


class FakeCompanyRepo:
    """No-op stand-in for CompanyRepository in pipeline tests.

    Real lookups are covered in test_company_leads.py — here we just
    need get_or_create to return None so the signal row gets a NULL
    company_id without exercising the lookup machinery."""

    def get_or_create_by_normalized_name(self, **_kwargs):
        return None


class FakeRawRepo:
    """Captures inserted raw items; mark_processed flips processed flag."""

    def __init__(self, dedupe_hashes: set[str] | None = None):
        self._dedupe = dedupe_hashes or set()
        self.inserted: list[RawSourceItem] = []
        self.processed_ids: set[UUID] = set()

    def insert_if_not_exists(self, item: RawSourceItem) -> RawSourceItem | None:
        if item.content_hash in self._dedupe:
            return None
        # Simulate the DB-assigned id
        if item.id is None:
            item.id = uuid4()
        self._dedupe.add(item.content_hash)
        self.inserted.append(item)
        return item

    def mark_processed(self, item: RawSourceItem) -> None:
        self.processed_ids.add(item.id)


class FakeSignalRepo:
    def __init__(self, existing_hashes: set[str] | None = None):
        self._existing = existing_hashes or set()
        self.added = []

    def find_by_signal_hash(self, h: str):
        return SimpleNamespace(signal_hash=h) if h in self._existing else None

    def add(self, signal):
        if signal.id is None:
            signal.id = uuid4()
        self.added.append(signal)
        return signal


class FakeRunRepo:
    def __init__(self):
        self.added = []
        self.finished = []

    def add(self, run):
        if run.id is None:
            run.id = uuid4()
        self.added.append(run)
        return run

    def mark_finished(
        self,
        run,
        *,
        status,
        items_collected,
        items_new,
        signals_detected,
        error_message=None,
    ):
        run.status = status.value
        run.items_collected = items_collected
        run.items_new = items_new
        run.signals_detected = signals_detected
        run.error_message = error_message
        self.finished.append(run)


class FakeDetector(SignalDetector):
    """Returns a canned SignalResult; can also be primed to raise."""

    def __init__(
        self,
        result: SignalResult | None = None,
        *,
        raise_on_titles: Iterable[str] = (),
    ):
        # Skip parent __init__ — we don't want to construct LlmVerifier.
        self._result = result
        self._raise_on_titles = set(raise_on_titles)
        self.calls = 0

    def detect(self, *, source_type, title, url, content, preferences=None):
        self.calls += 1
        if title in self._raise_on_titles:
            raise RuntimeError(f"boom for {title!r}")
        return self._result or SignalResult(prompt_version="v2")


class StaticCollector(BaseCollector):
    """Module-level so registry.get_collector can return it."""

    source_type = SourceType.NEWS.value
    items: list[SourceItem] = []

    def collect(self, _source):
        return list(self.items)


@pytest.fixture
def fake_news_collector(monkeypatch):
    """Inject StaticCollector into the registry for the duration of a test."""
    original = registry._REGISTRY.copy()
    registry._REGISTRY[SourceType.NEWS.value] = StaticCollector
    try:
        yield StaticCollector
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(original)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _build_service(
    *,
    source=None,
    sources=None,
    tenant_id=None,
    pref=None,
    raws=None,
    signals=None,
    runs=None,
    detector=None,
):
    """Wire up a PipelineService with fakes for every dependency.

    Pass either `source` (single) or `sources` (list). Defaults to
    tenant_id=uuid4() if not provided."""
    if source is not None and sources is None:
        sources = [source]
    sources = sources or []

    db = FakeSession()
    service = PipelineService.__new__(PipelineService)
    service.db = db
    service.tenant_id = tenant_id or uuid4()
    service.platform_sources = FakePlatformSourceRepo(sources)
    service.preferences = FakePreferenceRepo(pref)
    service.raws = raws or FakeRawRepo()
    service.signals = signals or FakeSignalRepo()
    service.runs = runs or FakeRunRepo()
    service.companies = FakeCompanyRepo()
    service._detector_factory = lambda: detector or FakeDetector()
    # __init__ is skipped via __new__; mirror its config-derived attrs.
    service._max_items_per_run = 0  # 0 disables the cap in tests
    return service, db


def _make_source(source_type=SourceType.NEWS, *, priority=100, is_active=True):
    """Platform-pool source: tenant_id=None to satisfy the new model."""
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=None,
        source_type=source_type.value,
        config={},
        is_active=is_active,
        priority=priority,
    )


def _make_pref(*, is_active=True):
    """Active preference. The fake matcher only checks `is_active` —
    tag intersection is covered in test_platform_source_matcher.py."""
    return SimpleNamespace(is_active=is_active)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_run_for_source_inserts_signal_on_match(fake_news_collector):
    """Happy path: collector produces an item that the prefilter and the
    (fake) detector both flag → one signal row inserted."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-1",
            title="Acme opens new warehouse in Memphis",
            url="https://example.com/news/1",
            content="Ribbon cutting today; new distribution center on-site.",
        )
    ]
    detector_result = SignalResult(
        prompt_version="v2",
        signal_type=SignalType.NEW_WAREHOUSE,
        confidence=Decimal("0.900"),
        company_name="Acme",
        target_customer_type="distributor",
        sector="retail",
        region="turkey",
        detected_event="Acme opens a new warehouse in Memphis",
    )
    detector = FakeDetector(result=detector_result)
    source = _make_source()
    service, db = _build_service(source=source, detector=detector)

    summary = service.run_for_source(source.id)

    assert summary.status == PipelineRunStatus.SUCCESS
    assert summary.collected_item_count == 1
    assert summary.inserted_signal_count == 1
    assert summary.failed_item_count == 0
    assert detector.calls == 1
    assert len(service.signals.added) == 1
    assert service.signals.added[0].company_name == "Acme"
    assert service.signals.added[0].region == "turkey"
    assert db.savepoints == 1  # per-item savepoint exercised


def test_prefilter_miss_skips_llm(fake_news_collector):
    """Item without business keywords must not trigger the detector.

    Lifestyle / non-business news is dropped at the broad gate before
    the verifier runs — this is the cost guardrail that keeps the LLM
    bill bounded for noisy collectors."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-2",
            title="Local farmer wins photo contest",
            url=None,
            content=(
                "The annual photo contest celebrated rural life with a "
                "showcase of weekend hobbyist work, drawing visitors from "
                "neighboring villages over the weekend."
            ),
        )
    ]
    detector = FakeDetector()
    source = _make_source()
    service, _ = _build_service(source=source, detector=detector)

    summary = service.run_for_source(source.id)

    assert detector.calls == 0
    assert summary.inserted_signal_count == 0
    assert summary.collected_item_count == 1
    assert summary.failed_item_count == 0


def test_duplicate_signal_hash_is_dropped(fake_news_collector):
    """Pre-existing signal_hash for the tenant: detect runs but no insert."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-3",
            title="Acme opens new warehouse in Memphis",
            url=None,
            content="Ribbon cutting today.",
        )
    ]
    detector_result = SignalResult(
        prompt_version="v2",
        signal_type=SignalType.NEW_WAREHOUSE,
        confidence=Decimal("0.900"),
        company_name="Acme",
        target_customer_type="distributor",
        region="turkey",
    )
    # Pre-seed the same hash that PipelineService will compute.
    from app.core.hashing import signal_hash

    seeded = {
        signal_hash(
            signal_type="new_warehouse",
            company_name="Acme",
            region="turkey",
            target_customer_type="distributor",
        )
    }
    signals = FakeSignalRepo(existing_hashes=seeded)
    source = _make_source()
    service, _ = _build_service(
        source=source, signals=signals, detector=FakeDetector(result=detector_result)
    )

    summary = service.run_for_source(source.id)

    assert summary.inserted_signal_count == 0
    assert signals.added == []  # nothing inserted


def test_run_for_tenant_skips_when_no_preferences(fake_news_collector):
    """Tenant without any preference row → 0 source runs, no error."""
    fake_news_collector.items = []  # would never be reached
    service, _ = _build_service(pref=None)

    summary = service.run_for_tenant()

    assert summary.source_run_count == 0
    assert summary.collected_item_count == 0
    assert summary.inserted_signal_count == 0


def test_run_for_tenant_skips_when_preferences_inactive(fake_news_collector):
    """is_active=false on the preference row pauses the tenant entirely
    even if matching sources exist."""
    source = _make_source()
    service, _ = _build_service(source=source, pref=_make_pref(is_active=False))

    summary = service.run_for_tenant()

    assert summary.source_run_count == 0


def test_run_for_tenant_runs_matched_sources_in_priority_order(fake_news_collector):
    """Matched sources are dispatched in priority asc, id asc order."""
    fake_news_collector.items = []  # collector returns no items: 0-collected runs
    s_low = _make_source(priority=10)
    s_mid = _make_source(priority=50)
    s_high = _make_source(priority=200)
    # Pass them out of order to prove the matcher orders them.
    service, _ = _build_service(
        sources=[s_high, s_low, s_mid], pref=_make_pref()
    )

    summary = service.run_for_tenant()

    run_source_ids = [r.source_id for r in summary.source_runs]
    assert run_source_ids == [s_low.id, s_mid.id, s_high.id]
    assert summary.source_run_count == 3
    assert summary.failed_run_count == 0


def test_export_expansion_news_produces_signal(fake_news_collector):
    """End-to-end wiring: a clean export-expansion news item passes the
    gate, the (fake) verifier returns a v2 lead, the row is persisted
    with the new fields populated."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-export",
            title="ABC Foods to begin exports to Germany next quarter",
            url="https://example.com/news/abc",
            content=(
                "ABC Foods announced it will expand exports across the "
                "European market starting next quarter, with shipments "
                "originating from its Turkey production hub."
            ),
        )
    ]
    detector_result = SignalResult(
        prompt_version="v2",
        signal_type=SignalType.EXPORT_EXPANSION,
        confidence=Decimal("0.780"),
        company_name="ABC Foods",
        target_customer_type="exporter",
        sector="food",
        region="eu",
        detected_event="ABC Foods is launching exports to Germany",
        why_relevant_for_logistics="Cross-border road freight required",
        recommended_services=["road_freight", "customs_brokerage"],
        urgency="medium",
    )
    service, _ = _build_service(
        source=_make_source(), detector=FakeDetector(result=detector_result)
    )

    summary = service.run_for_source(service.platform_sources._sources[0].id)

    assert summary.inserted_signal_count == 1
    persisted = service.signals.added[0]
    assert persisted.signal_type == "export_expansion"
    assert persisted.target_customer_type == "exporter"
    assert persisted.region == "eu"
    assert "road_freight" in persisted.recommended_services


def test_signal_with_missing_company_is_dropped(fake_news_collector):
    """Deterministic guardrail: even if the verifier returns is_signal
    semantics, the company guard in SignalResult.is_signal collapses
    it to False and no row is written."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-noco",
            title="Sector-wide capacity increase reported in logistics",
            url=None,
            content=(
                "Industry analysts report broad capacity increases across "
                "the logistics sector in Turkey, with multiple unnamed "
                "operators expanding warehouses."
            ),
        )
    ]
    no_company = SignalResult(
        prompt_version="v2",
        signal_type=SignalType.CAPACITY_INCREASE,
        confidence=Decimal("0.500"),
        company_name=None,  # the deterministic guard fires here
        region="turkey",
    )
    service, _ = _build_service(
        source=_make_source(), detector=FakeDetector(result=no_company)
    )

    summary = service.run_for_source(service.platform_sources._sources[0].id)

    assert summary.inserted_signal_count == 0
    assert service.signals.added == []


def test_llm_failure_does_not_crash_pipeline(fake_news_collector):
    """A verifier that raises is caught at the per-item SAVEPOINT.
    The run reports the failure without aborting and without losing
    earlier signals from the same source run."""
    fake_news_collector.items = [
        SourceItem(
            external_id="boom",
            title="Globex opens new distribution center for export",
            url=None,
            content=(
                "Globex announced a new distribution center to support its "
                "EU export operations beginning this quarter."
            ),
        )
    ]
    detector = FakeDetector(
        result=SignalResult(prompt_version="v2"),
        raise_on_titles=["Globex opens new distribution center for export"],
    )
    service, _ = _build_service(source=_make_source(), detector=detector)

    summary = service.run_for_source(service.platform_sources._sources[0].id)

    assert summary.status == PipelineRunStatus.SUCCESS
    assert summary.failed_item_count == 1
    assert summary.inserted_signal_count == 0


def test_run_for_tenant_skips_inactive_sources(fake_news_collector):
    """is_active=false on the source excludes it from matching."""
    fake_news_collector.items = []
    active = _make_source(is_active=True)
    inactive = _make_source(is_active=False)
    service, _ = _build_service(
        sources=[active, inactive], pref=_make_pref()
    )

    summary = service.run_for_tenant()

    assert summary.source_run_count == 1
    assert summary.source_runs[0].source_id == active.id


def test_item_failure_is_isolated(fake_news_collector):
    """One bad item must not abort the rest of the run."""
    fake_news_collector.items = [
        SourceItem(
            external_id="bad",
            title="Acme opens new warehouse — boom item",
            url=None,
            content="Ribbon cutting today.",
        ),
        SourceItem(
            external_id="ok",
            title="Globex opens new distribution center",
            url=None,
            content="New DC in Austin opens this week.",
        ),
    ]
    good_result = SignalResult(
        prompt_version="v2",
        signal_type=SignalType.NEW_WAREHOUSE,
        confidence=Decimal("0.800"),
        company_name="Globex",
        target_customer_type="distributor",
        region="global",
    )
    detector = FakeDetector(
        result=good_result,
        raise_on_titles=["Acme opens new warehouse — boom item"],
    )
    source = _make_source()
    service, db = _build_service(source=source, detector=detector)

    summary = service.run_for_source(source.id)

    assert summary.status == PipelineRunStatus.SUCCESS
    assert summary.failed_item_count == 1
    assert summary.inserted_signal_count == 1
    assert db.savepoints == 2  # one savepoint per processed item
