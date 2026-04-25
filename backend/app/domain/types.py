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
    invalid (unknown signal_type, out-of-range confidence, junk fields);
    normalization into SignalResult handles that."""

    prompt_version: str
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
    - Promoted fields are split out of the LLM's extracted_fields; the
      rest goes to `extra` (persisted as JSONB).
    """

    prompt_version: str
    signal_type: SignalType | None = None
    confidence: Decimal = Decimal("0.000")
    company_name: str | None = None
    location: str | None = None
    role_title: str | None = None
    supplier_name: str | None = None
    summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signal(self) -> bool:
        return self.signal_type is not None


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
