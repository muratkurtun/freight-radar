"""Pipeline service tests.

The orchestrator pulls together a collector, a candidate prefilter, an
LLM verifier and four repositories. These tests bypass the real DB by
constructing PipelineService directly via __new__ and wiring in fakes
for every repo + the detector. The collector is registered through the
public registry so the source-type dispatch path is also exercised.
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


class FakeSourceRepo:
    def __init__(self, source):
        self._source = source

    def list_active(self):
        return [self._source]

    def get_or_404(self, _id):
        return self._source


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

    def detect(self, *, source_type, title, url, content, candidate_hints=None):
        self.calls += 1
        if title in self._raise_on_titles:
            raise RuntimeError(f"boom for {title!r}")
        return self._result or SignalResult(prompt_version="v1")


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
    source,
    raws=None,
    signals=None,
    runs=None,
    detector=None,
):
    db = FakeSession()
    service = PipelineService.__new__(PipelineService)
    service.db = db
    service.tenant_id = source.tenant_id
    service.sources = FakeSourceRepo(source)
    service.raws = raws or FakeRawRepo()
    service.signals = signals or FakeSignalRepo()
    service.runs = runs or FakeRunRepo()
    service._detector_factory = lambda: detector or FakeDetector()
    return service, db


def _make_source(source_type=SourceType.NEWS):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        source_type=source_type.value,
        config={},
    )


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
        prompt_version="v1",
        signal_type=SignalType.WAREHOUSE_OPENING,
        confidence=Decimal("0.900"),
        company_name="Acme",
        location="Memphis",
        summary="Acme opens new DC.",
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
    assert db.savepoints == 1  # per-item savepoint exercised


def test_prefilter_miss_skips_llm(fake_news_collector):
    """Item without keyword hits must not trigger the detector."""
    fake_news_collector.items = [
        SourceItem(
            external_id="ext-2",
            title="Quarterly results steady",
            url=None,
            content="Revenue flat year over year.",
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
        prompt_version="v1",
        signal_type=SignalType.WAREHOUSE_OPENING,
        confidence=Decimal("0.900"),
        company_name="Acme",
        location="Memphis",
    )
    # Pre-seed the same hash that PipelineService will compute.
    from app.core.hashing import signal_hash

    seeded = {
        signal_hash(
            signal_type="warehouse_opening",
            company_name="Acme",
            location="Memphis",
            role_title=None,
            supplier_name=None,
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
        prompt_version="v1",
        signal_type=SignalType.WAREHOUSE_OPENING,
        confidence=Decimal("0.800"),
        company_name="Globex",
        location="Austin",
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
