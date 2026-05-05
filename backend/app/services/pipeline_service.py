"""Pipeline orchestration layer.

Responsibilities:
    collect -> persist raw -> prefilter -> AI verify -> map -> persist signal
    (pending_review) -> close pipeline_run

This module is orchestration only. It must not contain HTTP parsing,
SQL, prompt engineering, or LLM calls — those live in the collectors,
repositories and detectors respectively. A rewrite of this file should
leave those layers untouched.

Failure isolation
-----------------
Three failure scopes, from outer to inner:

* Tenant-level: a single tenant blowing up (e.g. DB connection lost) is
  caught by `run_pipeline_for_all_active_tenants` so other tenants keep
  running.
* Source-level: a collector crash or a DB error while writing the run
  row marks that PipelineRun FAILED and moves on to the next source.
* Item-level: per-item detection runs inside a SAVEPOINT so one bad raw
  item (LLM 500, JSON parse error, etc.) can't roll back signals already
  persisted from earlier items in the same source run. The item stays
  `processed_at IS NULL` so it can be retried later.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.collectors.registry import get_collector
from app.config import get_settings
from app.core.errors import NotFoundError
from app.core.hashing import content_hash, signal_hash
from app.core.logging import get_logger
from app.detectors.candidate_detector import should_call_llm
from app.detectors.signal_detector import SignalDetector
from app.domain.enums import PipelineRunStatus, ReviewStatus
from app.domain.models import (
    DetectedSignal,
    PipelineRun,
    RawSourceItem,
    Source,
    TenantSignalPreference,
)
from app.domain.types import SignalResult, SourceItem
from app.repositories.companies import CompanyRepository
from app.repositories.pipeline_runs import PipelineRunRepository
from app.repositories.platform_sources import PlatformSourceRepository
from app.repositories.raw_items import RawItemRepository
from app.repositories.signals import SignalRepository
from app.repositories.tenant_preferences import TenantPreferenceRepository
from app.repositories.tenants import TenantRepository

logger = get_logger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceRunSummary:
    """Detached summary of one PipelineRun, safe to hand back to callers
    after the DB session is closed."""

    source_id: UUID
    run_id: UUID
    status: PipelineRunStatus
    collected_item_count: int
    inserted_signal_count: int
    failed_item_count: int
    error_message: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class TenantPipelineSummary:
    """Aggregated result of running the pipeline for every active source
    of a single tenant."""

    tenant_id: UUID
    started_at: datetime
    finished_at: datetime
    source_run_count: int
    succeeded_run_count: int
    failed_run_count: int
    collected_item_count: int
    inserted_signal_count: int
    failed_item_count: int
    source_runs: list[SourceRunSummary]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineService:
    """Tenant-scoped pipeline orchestrator.

    One instance per tenant per DB session. Instantiates its own
    repositories from the shared session; the caller owns the session
    lifecycle."""

    def __init__(self, db: Session, tenant_id: UUID, *, detector: SignalDetector | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.platform_sources = PlatformSourceRepository(db)
        self.preferences = TenantPreferenceRepository(db, tenant_id)
        self.raws = RawItemRepository(db, tenant_id)
        self.signals = SignalRepository(db, tenant_id)
        self.runs = PipelineRunRepository(db, tenant_id)
        self.companies = CompanyRepository(db, tenant_id)
        self._detector_factory = lambda: detector or SignalDetector()
        self._max_items_per_run = get_settings().max_items_per_source_run

    # ------------------------------------------------------------------
    # public entry points
    # ------------------------------------------------------------------

    def run_for_tenant(self) -> TenantPipelineSummary:
        """Run the pipeline against the platform sources matching this
        tenant's preferences.

        Per-source failures are recorded as FAILED PipelineRun rows and
        do not abort the tenant run; they surface in the summary.

        Behaviour when the tenant has no usable preferences:
        - no preference row at all → returns an empty summary, logs reason
        - is_active=false          → same
        - empty preference arrays  → matching naturally returns 0 sources
        """
        started_at = _utcnow()
        prefs = self.preferences.get()
        if prefs is None:
            logger.info(
                "Tenant pipeline skipped tenant=%s reason=no_preferences",
                self.tenant_id,
            )
            return self._empty_summary(started_at)
        if not prefs.is_active:
            logger.info(
                "Tenant pipeline skipped tenant=%s reason=preferences_inactive",
                self.tenant_id,
            )
            return self._empty_summary(started_at)

        active_sources = self.platform_sources.match_for_preferences(prefs)
        logger.info(
            "Tenant pipeline started tenant=%s matched_sources=%d",
            self.tenant_id,
            len(active_sources),
        )

        summaries: list[SourceRunSummary] = [
            self._run_and_summarize(source) for source in active_sources
        ]

        finished_at = _utcnow()
        summary = TenantPipelineSummary(
            tenant_id=self.tenant_id,
            started_at=started_at,
            finished_at=finished_at,
            source_run_count=len(summaries),
            succeeded_run_count=sum(
                1 for s in summaries if s.status == PipelineRunStatus.SUCCESS
            ),
            failed_run_count=sum(
                1 for s in summaries if s.status == PipelineRunStatus.FAILED
            ),
            collected_item_count=sum(s.collected_item_count for s in summaries),
            inserted_signal_count=sum(s.inserted_signal_count for s in summaries),
            failed_item_count=sum(s.failed_item_count for s in summaries),
            source_runs=summaries,
        )
        logger.info(
            "Tenant pipeline finished tenant=%s runs=%d ok=%d failed=%d "
            "collected=%d signals=%d item_errors=%d",
            self.tenant_id,
            summary.source_run_count,
            summary.succeeded_run_count,
            summary.failed_run_count,
            summary.collected_item_count,
            summary.inserted_signal_count,
            summary.failed_item_count,
        )
        return summary

    def run_for_source(self, source_id: UUID) -> SourceRunSummary:
        """Run the pipeline against a single platform source for this
        tenant. Used by tests and ad-hoc admin tooling — production
        scheduling goes through `run_for_tenant`."""
        source = self.platform_sources.get(source_id)
        if source is None:
            raise NotFoundError(f"Source {source_id} not found")
        return self._run_and_summarize(source)

    def _empty_summary(self, started_at: datetime) -> TenantPipelineSummary:
        finished_at = _utcnow()
        return TenantPipelineSummary(
            tenant_id=self.tenant_id,
            started_at=started_at,
            finished_at=finished_at,
            source_run_count=0,
            succeeded_run_count=0,
            failed_run_count=0,
            collected_item_count=0,
            inserted_signal_count=0,
            failed_item_count=0,
            source_runs=[],
        )

    # ------------------------------------------------------------------
    # per-source orchestration
    # ------------------------------------------------------------------

    def _run_and_summarize(self, source: Source) -> SourceRunSummary:
        run = PipelineRun(tenant_id=self.tenant_id, source_id=source.id)
        self.runs.add(run)
        self.db.commit()

        logger.info(
            "Source run started tenant=%s source=%s run=%s",
            self.tenant_id,
            source.id,
            run.id,
        )

        collected_item_count = 0
        items_new = 0
        inserted_signal_count = 0
        failed_item_count = 0

        try:
            collector = get_collector(source.source_type)
            collected = collector.collect(source)
            collected_item_count = len(collected)

            new_items = self._persist_new_items(source, collected, run.id)
            items_new = len(new_items)

            # Per-source-run cap: protect the OpenAI bill from a single
            # collector dumping hundreds of new items in one tick. The
            # OpenAI Console hard limit is the real bill cap; this is
            # just an in-app guard and is logged when it bites so we
            # know the cap is the operative reason items got skipped.
            cap = self._max_items_per_run
            llm_eligible = new_items
            if cap > 0 and len(new_items) > cap:
                logger.warning(
                    "Per-run cap reached tenant=%s source=%s new=%d cap=%d "
                    "(%d items deferred to next run)",
                    self.tenant_id, source.id, len(new_items), cap,
                    len(new_items) - cap,
                )
                llm_eligible = new_items[:cap]

            if llm_eligible:
                detector = self._detector_factory()
                prefs = self.preferences.get()
                inserted_signal_count, failed_item_count = self._detect_and_persist(
                    source, llm_eligible, detector, prefs
                )

            self.runs.mark_finished(
                run,
                status=PipelineRunStatus.SUCCESS,
                items_collected=collected_item_count,
                items_new=items_new,
                signals_detected=inserted_signal_count,
            )
            self.db.commit()

            logger.info(
                "Source run finished tenant=%s source=%s run=%s "
                "collected=%d new=%d signals=%d item_errors=%d",
                self.tenant_id,
                source.id,
                run.id,
                collected_item_count,
                items_new,
                inserted_signal_count,
                failed_item_count,
            )

            return SourceRunSummary(
                source_id=source.id,
                run_id=run.id,
                status=PipelineRunStatus.SUCCESS,
                collected_item_count=collected_item_count,
                inserted_signal_count=inserted_signal_count,
                failed_item_count=failed_item_count,
                error_message=None,
            )
        except Exception as exc:
            logger.exception(
                "Source run failed tenant=%s source=%s run=%s",
                self.tenant_id,
                source.id,
                run.id,
            )
            self.db.rollback()
            run = self.db.merge(run)
            error_message = str(exc)[:2000]
            self.runs.mark_finished(
                run,
                status=PipelineRunStatus.FAILED,
                items_collected=collected_item_count,
                items_new=items_new,
                signals_detected=inserted_signal_count,
                error_message=error_message,
            )
            self.db.commit()
            return SourceRunSummary(
                source_id=source.id,
                run_id=run.id,
                status=PipelineRunStatus.FAILED,
                collected_item_count=collected_item_count,
                inserted_signal_count=inserted_signal_count,
                failed_item_count=failed_item_count,
                error_message=error_message,
            )

    # ------------------------------------------------------------------
    # stage helpers
    # ------------------------------------------------------------------

    def _persist_new_items(
        self, source: Source, collected: list[SourceItem], run_id: UUID
    ) -> list[RawSourceItem]:
        new_items: list[RawSourceItem] = []
        for dto in collected:
            item = RawSourceItem(
                tenant_id=self.tenant_id,
                source_id=source.id,
                pipeline_run_id=run_id,
                external_id=dto.external_id,
                url=dto.url,
                title=dto.title,
                content=dto.content,
                content_hash=content_hash(title=dto.title, content=dto.content),
                published_at=dto.published_at,
            )
            inserted = self.raws.insert_if_not_exists(item)
            if inserted is not None:
                new_items.append(inserted)
        if new_items:
            self.db.commit()
        return new_items

    def _detect_and_persist(
        self,
        source: Source,
        items: list[RawSourceItem],
        detector: SignalDetector,
        preferences: TenantSignalPreference | None,
    ) -> tuple[int, int]:
        """Returns (inserted_signal_count, failed_item_count).

        Each item is wrapped in a SAVEPOINT so a failure on one item
        (LLM error, JSON parse error, integrity error, ...) rolls back
        only that item's partial writes and leaves earlier signals
        intact. Failed items keep processed_at NULL so a later run can
        retry them.

        Cost visibility: tracks how many items actually called the LLM
        (i.e. passed the candidate gate) and logs it at the end of the
        per-source run. The OpenAI Console hard limit is still the real
        bill cap; this just tells us where the tokens went."""
        inserted = 0
        failed = 0
        llm_calls = 0
        gate_skips = 0
        for item in items:
            try:
                with self.db.begin_nested():
                    detected, called_llm = self._detect_one(
                        source, item, detector, preferences
                    )
                    if called_llm:
                        llm_calls += 1
                    else:
                        gate_skips += 1
                    if detected:
                        inserted += 1
                    self.raws.mark_processed(item)
            except Exception:
                failed += 1
                logger.exception(
                    "Item detection failed tenant=%s source=%s item=%s",
                    self.tenant_id,
                    source.id,
                    item.id,
                )
        self.db.commit()
        logger.info(
            "Detection finished tenant=%s source=%s items=%d llm_calls=%d "
            "gate_skips=%d signals=%d failures=%d",
            self.tenant_id, source.id, len(items), llm_calls, gate_skips,
            inserted, failed,
        )
        return inserted, failed

    def _detect_one(
        self,
        source: Source,
        item: RawSourceItem,
        detector: SignalDetector,
        preferences: TenantSignalPreference | None,
    ) -> tuple[bool, bool]:
        """Gate + LLM verify + map + persist for one raw item.

        Returns `(inserted, called_llm)`:
          - inserted=True only when a NEW signal row was persisted
          - called_llm reflects whether the candidate gate let this item
            through and the verifier was actually invoked. Gate misses,
            LLM non-signals, and duplicate signal_hash hits all set
            inserted=False without raising."""
        if not should_call_llm(
            source_type=source.source_type,
            title=item.title,
            content=item.content,
        ):
            logger.debug("Gate miss item=%s", item.id)
            return False, False

        result = detector.detect(
            source_type=source.source_type,
            title=item.title,
            url=item.url,
            content=item.content,
            preferences=preferences,
        )
        if not result.is_signal:
            return False, True
        return self._persist_signal(item, result), True

    def _persist_signal(self, item: RawSourceItem, result: SignalResult) -> bool:
        """Insert a detected_signals row in pending_review state.

        Returns False when an existing signal shares the same
        signal_hash (same type + same subject) for this tenant — the
        duplicate is silently dropped. The UNIQUE(tenant_id, signal_hash)
        constraint is the authoritative guard; this pre-check just
        avoids the IntegrityError on the common case."""
        assert result.signal_type is not None  # guarded by is_signal
        shash = signal_hash(
            signal_type=result.signal_type.value,
            company_name=result.company_name,
            region=result.region,
            target_customer_type=result.target_customer_type,
        )
        if self.signals.find_by_signal_hash(shash) is not None:
            logger.debug(
                "Duplicate signal skipped tenant=%s item=%s hash=%s",
                self.tenant_id,
                item.id,
                shash,
            )
            return False

        # Resolve / create the tenant-scoped Company entity. Returns
        # None when the LLM did not extract a usable company name —
        # SignalResult.is_signal already guards against empty company
        # before we reach this point, but keep the defensive check.
        company = self.companies.get_or_create_by_normalized_name(
            raw_name=result.company_name or "",
            sector=result.sector,
            region=result.region,
        )

        signal = DetectedSignal(
            tenant_id=self.tenant_id,
            raw_source_item_id=item.id,
            signal_type=result.signal_type.value,
            confidence=result.confidence,
            signal_hash=shash,
            company_id=company.id if company is not None else None,
            company_name=result.company_name,
            # v2 logistics-lead fields
            target_customer_type=result.target_customer_type,
            sector=result.sector,
            region=result.region,
            detected_event=result.detected_event,
            why_relevant_for_logistics=result.why_relevant_for_logistics,
            potential_logistics_need=result.potential_logistics_need,
            recommended_services=list(result.recommended_services),
            urgency=result.urgency,
            suggested_sales_action=result.suggested_sales_action,
            suggested_outreach_message=result.suggested_outreach_message,
            evidence_snippet=result.evidence_snippet,
            extra=result.extra,
            prompt_version=result.prompt_version,
            review_status=ReviewStatus.PENDING_REVIEW.value,
        )
        self.signals.add(signal)
        return True


# ----------------------------------------------------------------------
# module-level entry points (preferred callers from scheduler / scripts)
# ----------------------------------------------------------------------


def run_pipeline_for_tenant(db: Session, tenant_id: UUID) -> TenantPipelineSummary:
    """Run the pipeline for a single tenant across all its active sources."""
    return PipelineService(db, tenant_id).run_for_tenant()


def run_pipeline_for_all_active_tenants(db: Session) -> list[TenantPipelineSummary]:
    """Run the pipeline for every active tenant sequentially.

    A crash at the tenant level (e.g. session corruption) is logged and
    skipped so other tenants still get processed. The returned list only
    contains summaries for tenants whose run completed."""
    tenants = TenantRepository(db).list_active()
    summaries: list[TenantPipelineSummary] = []
    for tenant in tenants:
        try:
            summaries.append(run_pipeline_for_tenant(db, tenant.id))
        except Exception:
            logger.exception("Tenant pipeline failed tenant=%s", tenant.id)
            db.rollback()
    return summaries
