"""Pure-Python domain types used between pipeline stages.

These are frozen dataclasses (immutable, slotted) so they can be passed
between collectors, detectors and services without risk of mutation and
without any SQLAlchemy session coupling. They are NOT the persistence
models (see app.domain.models) and NOT the HTTP DTOs (see
app.domain.schemas); they are the internal data interchange types.

tenant_id rules:
  - SourceItem / LlmOutput / SignalResult: NO tenant_id. These flow
    below the tenant-aware orchestration layer and are injected into
    tenant scope only at persist time.
  - SignalReview / PipelineRun: carry tenant_id. They represent
    tenant-scoped domain events or summaries and must stay attributable
    when handed to callers outside the DB session.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from app.domain.enums import PipelineRunStatus, SignalType

ReviewAction = Literal["approve", "reject"]


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceItem:
    """One item fetched by a collector, before any persistence or analysis."""

    external_id: str
    content: str
    title: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True, frozen=True)
class LlmOutput:
    """Raw parsed LLM response, before validation/normalization.

    Mirrors the JSON shape requested by the prompt. Values may be
    invalid (unknown signal_type, out-of-range confidence, off-vocab
    enum); normalization into SignalResult handles that.

    `is_signal` is the LLM's own boolean — distinct from the
    derived-from-signal_type one in SignalResult — so that a LLM that
    returns is_signal=false with an inadvertently-set signal_type still
    short-circuits at the orchestration layer.
    """

    prompt_version: str
    is_signal: bool = False
    signal_type: str | None = None
    confidence: float = 0.0
    extracted_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True, frozen=True)
class SignalResult:
    """Normalized detector output. Ready to persist as a detected_signals row.

    - signal_type: validated against SignalType, or None when the LLM
      did not identify a signal.
    - confidence: clamped to [0, 1], quantized to 3 decimal places to
      match the NUMERIC(4,3) column.
    - Pre-pivot fields (location, role_title, supplier_name, summary)
      are kept on the dataclass for back-compat with legacy code paths,
      but are not populated by the v2 detector.
    - Logistics lead fields (target_customer_type, sector, region,
      detected_event, why_relevant_for_logistics, potential_logistics_need,
      recommended_services, urgency, suggested_sales_action,
      suggested_outreach_message, evidence_snippet) are the v2 output.
    - extra: anything the LLM returned outside the known schema.
    """

    prompt_version: str
    signal_type: SignalType | None = None
    confidence: Decimal = Decimal("0.000")
    company_name: str | None = None

    # Pre-pivot fields — kept nullable for back-compat with legacy
    # callers / tests; v2 leaves them None.
    location: str | None = None
    role_title: str | None = None
    supplier_name: str | None = None
    summary: str | None = None

    # Logistics lead fields (v2).
    target_customer_type: str | None = None
    sector: str | None = None
    region: str | None = None
    detected_event: str | None = None
    why_relevant_for_logistics: str | None = None
    potential_logistics_need: str | None = None
    recommended_services: list[str] = field(default_factory=list)
    urgency: str | None = None
    suggested_sales_action: str | None = None
    suggested_outreach_message: str | None = None
    evidence_snippet: str | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signal(self) -> bool:
        # A signal requires both a known type AND a company_name. The
        # company guard implements the deterministic rule: no company
        # named in the text → not actionable for sales, drop.
        return self.signal_type is not None and bool(self.company_name)


@dataclass(slots=True, kw_only=True, frozen=True)
class SignalReview:
    """Domain snapshot of a signal_reviews row, detached from the ORM."""

    id: UUID
    tenant_id: UUID
    detected_signal_id: UUID
    reviewer_user_id: UUID
    action: ReviewAction
    reason: str | None
    created_at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class PipelineRun:
    """Domain snapshot of a pipeline_runs row, detached from the ORM."""

    id: UUID
    tenant_id: UUID
    source_id: UUID
    status: PipelineRunStatus
    started_at: datetime
    finished_at: datetime | None
    items_collected: int
    items_new: int
    signals_detected: int
    error_message: str | None
