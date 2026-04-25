from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import (
    PipelineRunStatus,
    ReviewStatus,
    UserRole,
)


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "subscription_status IN ('trial','active')",
            name="ck_tenants_subscription_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subscription_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_app_users_tenant_email"),
        CheckConstraint(
            "role IN ('platform_admin','tenant_admin','tenant_user')",
            name="ck_app_users_role",
        ),
        Index("ix_app_users_tenant", "tenant_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default=UserRole.TENANT_USER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "url", name="uq_sources_tenant_url"),
        CheckConstraint(
            "source_type IN ('news','job_board','company_website')",
            name="ck_sources_source_type",
        ),
        Index("ix_sources_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','success','failed')", name="ck_pipeline_runs_status"
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_pipeline_runs_finish",
        ),
        Index("ix_pipeline_runs_tenant_started", "tenant_id", "started_at"),
        Index("ix_pipeline_runs_source_started", "source_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PipelineRunStatus.RUNNING.value
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RawSourceItem(Base):
    __tablename__ = "raw_source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_items_source_external"),
        UniqueConstraint("tenant_id", "content_hash", name="uq_raw_items_tenant_content"),
        Index("ix_raw_items_tenant_processed", "tenant_id", "processed_at"),
        Index("ix_raw_items_source", "source_id"),
        Index("ix_raw_items_run", "pipeline_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DetectedSignal(Base):
    __tablename__ = "detected_signals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "signal_hash", name="uq_signals_tenant_hash"),
        CheckConstraint(
            "signal_type IN ('warehouse_opening','supplier_change','hiring_supply_chain_role')",
            name="ck_signals_signal_type",
        ),
        CheckConstraint(
            "review_status IN ('pending_review','approved','rejected')",
            name="ck_signals_review_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_signals_confidence_range"
        ),
        Index("ix_signals_tenant_status", "tenant_id", "review_status"),
        Index("ix_signals_tenant_type", "tenant_id", "signal_type"),
        Index("ix_signals_tenant_created", "tenant_id", "created_at"),
        Index("ix_signals_raw_item", "raw_source_item_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    raw_source_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_source_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(precision=4, scale=3), nullable=False, default=Decimal("0")
    )
    signal_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReviewStatus.PENDING_REVIEW.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SignalReview(Base):
    __tablename__ = "signal_reviews"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approve','reject')", name="ck_signal_reviews_action"
        ),
        CheckConstraint(
            "action <> 'reject' OR reason IS NOT NULL",
            name="ck_signal_reviews_reject_reason",
        ),
        Index("ix_signal_reviews_signal", "detected_signal_id"),
        Index("ix_signal_reviews_tenant_created", "tenant_id", "created_at"),
        Index("ix_signal_reviews_user", "reviewer_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    detected_signal_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("detected_signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
