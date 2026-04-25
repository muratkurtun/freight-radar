from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.enums import (
    PipelineRunStatus,
    ReviewStatus,
    SignalType,
    SourceType,
    SubscriptionStatus,
    UserRole,
)
from app.domain.types import ReviewAction


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    user_id: UUID
    tenant_id: UUID
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    subscription_status: SubscriptionStatus
    trial_ends_at: datetime | None = None


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RegisterResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: CurrentUser


# ---- Sources ----

class SourceCreate(BaseModel):
    source_type: SourceType
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class SourceRead(ORMModel):
    id: UUID
    tenant_id: UUID
    source_type: SourceType
    name: str
    url: str
    config: dict[str, Any]
    is_active: bool
    created_at: datetime


# ---- Signals ----

class SignalRead(ORMModel):
    id: UUID
    tenant_id: UUID
    raw_source_item_id: UUID
    signal_type: SignalType
    confidence: Decimal
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None
    extra: dict[str, Any]
    prompt_version: str
    review_status: ReviewStatus
    created_at: datetime


class SignalReviewRead(ORMModel):
    id: UUID
    detected_signal_id: UUID
    reviewer_user_id: UUID
    action: ReviewAction
    reason: str | None
    created_at: datetime


class SignalDetail(SignalRead):
    raw_title: str | None
    raw_url: str | None
    raw_content: str
    latest_review: SignalReviewRead | None = None


# ---- Review ----

class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReviewDecisionRequest(BaseModel):
    """Single approve/reject endpoint payload. `reason` is required when
    `action="reject"` (enforced below)."""

    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> "ReviewDecisionRequest":
        if self.action == "reject" and not (self.reason and self.reason.strip()):
            raise ValueError("reason is required when action='reject'")
        return self


# ---- Opportunities ----

class OpportunityRead(BaseModel):
    signal_id: UUID
    signal_type: SignalType
    confidence: Decimal
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None
    created_at: datetime
    raw_title: str | None
    raw_url: str | None
    published_at: datetime | None
    source_id: UUID
    source_name: str
    source_type: SourceType


# ---- Feedback / analytics ----

class FalsePositiveRead(BaseModel):
    signal_id: UUID
    signal_type: SignalType
    confidence: Decimal
    prompt_version: str
    company_name: str | None
    location: str | None
    role_title: str | None
    supplier_name: str | None
    summary: str | None
    reject_reason: str
    rejected_at: datetime
    raw_title: str | None
    raw_url: str | None


class ApprovalStatsRead(BaseModel):
    approved: int
    rejected: int
    pending: int
    total: int
    approval_rate: float = Field(ge=0.0, le=1.0)


class ApprovalStatsByTypeRead(BaseModel):
    signal_type: SignalType
    stats: ApprovalStatsRead


class ApprovalStatsBySourceRead(BaseModel):
    source_id: UUID
    source_name: str
    source_type: SourceType
    stats: ApprovalStatsRead


# ---- Pipeline ----

class PipelineRunRead(ORMModel):
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


class PipelineTriggerResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    tenant_id: UUID
    message: str


# ---- Pagination ----

class Page(BaseModel):
    limit: int = 20
    offset: int = 0
    total: int


class PagedSignals(BaseModel):
    items: list[SignalRead]
    page: Page


class PagedSources(BaseModel):
    items: list[SourceRead]
    page: Page


class PagedOpportunities(BaseModel):
    items: list[OpportunityRead]
    page: Page


class PagedPipelineRuns(BaseModel):
    items: list[PipelineRunRead]
