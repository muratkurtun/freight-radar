"""Signal repository — detected_signals table.

A signal is born with `review_status = 'pending_review'`. Dedupe is by
`(tenant_id, signal_hash)` (enforced by UNIQUE constraint). Promotion
to 'approved'/'rejected' is an UPDATE here paired with an INSERT in
ReviewRepository — both live inside one transaction opened by the
caller (ReviewService)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.domain.enums import ReviewStatus, SignalType, SourceType
from app.domain.models import DetectedSignal, RawSourceItem, Source
from app.repositories.base import TenantAwareRepository


class SignalRepository(TenantAwareRepository[DetectedSignal]):
    model = DetectedSignal

    # --- reads ---

    def find_by_signal_hash(self, signal_hash: str) -> DetectedSignal | None:
        stmt = self._base_query().where(DetectedSignal.signal_hash == signal_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_with_raw(
        self, signal_id: UUID
    ) -> tuple[DetectedSignal, RawSourceItem] | None:
        stmt = (
            select(DetectedSignal, RawSourceItem)
            .join(RawSourceItem, RawSourceItem.id == DetectedSignal.raw_source_item_id)
            .where(DetectedSignal.tenant_id == self.tenant_id)
            .where(DetectedSignal.id == signal_id)
        )
        row = self.db.execute(stmt).first()
        return (row[0], row[1]) if row else None

    def list_filtered(
        self,
        *,
        signal_type: SignalType | None = None,
        review_status: ReviewStatus | None = None,
        source_type: SourceType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DetectedSignal], int]:
        """Paginated list + total count. Joins to sources only when a
        source_type filter is supplied, to avoid a 3-table join otherwise."""
        stmt = self._base_query()
        count_stmt = select(func.count(DetectedSignal.id)).where(
            DetectedSignal.tenant_id == self.tenant_id
        )

        if signal_type is not None:
            stmt = stmt.where(DetectedSignal.signal_type == signal_type.value)
            count_stmt = count_stmt.where(DetectedSignal.signal_type == signal_type.value)
        if review_status is not None:
            stmt = stmt.where(DetectedSignal.review_status == review_status.value)
            count_stmt = count_stmt.where(DetectedSignal.review_status == review_status.value)
        if source_type is not None:
            stmt = (
                stmt.join(RawSourceItem, RawSourceItem.id == DetectedSignal.raw_source_item_id)
                .join(Source, Source.id == RawSourceItem.source_id)
                .where(Source.source_type == source_type.value)
            )
            count_stmt = (
                count_stmt.join(
                    RawSourceItem, RawSourceItem.id == DetectedSignal.raw_source_item_id
                )
                .join(Source, Source.id == RawSourceItem.source_id)
                .where(Source.source_type == source_type.value)
            )

        stmt = stmt.order_by(DetectedSignal.created_at.desc()).limit(limit).offset(offset)
        items = list(self.db.execute(stmt).scalars().all())
        total = int(self.db.execute(count_stmt).scalar_one())
        return items, total

    def list_pending_review(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[DetectedSignal], int]:
        return self.list_filtered(
            review_status=ReviewStatus.PENDING_REVIEW, limit=limit, offset=offset
        )

    # --- writes ---

    def create_pending(
        self,
        *,
        raw_source_item_id: UUID,
        signal_type: SignalType,
        confidence: Decimal,
        signal_hash: str,
        company_name: str | None,
        target_customer_type: str | None = None,
        sector: str | None = None,
        region: str | None = None,
        detected_event: str | None = None,
        why_relevant_for_logistics: str | None = None,
        potential_logistics_need: str | None = None,
        recommended_services: list[str] | None = None,
        urgency: str | None = None,
        suggested_sales_action: str | None = None,
        suggested_outreach_message: str | None = None,
        evidence_snippet: str | None = None,
        extra: dict[str, Any],
        prompt_version: str,
    ) -> DetectedSignal | None:
        """Insert a new signal with review_status='pending_review'.

        Returns None if a signal with the same signal_hash already
        exists for this tenant (idempotent from the service's view).

        Pre-pivot fields (location, role_title, supplier_name, summary)
        are no longer accepted here — write paths produce v2 logistics
        leads only. Legacy rows in the table keep their old field
        values; they are read but never created via this constructor.
        """
        if self.find_by_signal_hash(signal_hash) is not None:
            return None
        signal = DetectedSignal(
            tenant_id=self.tenant_id,
            raw_source_item_id=raw_source_item_id,
            signal_type=signal_type.value,
            confidence=confidence,
            signal_hash=signal_hash,
            company_name=company_name,
            target_customer_type=target_customer_type,
            sector=sector,
            region=region,
            detected_event=detected_event,
            why_relevant_for_logistics=why_relevant_for_logistics,
            potential_logistics_need=potential_logistics_need,
            recommended_services=list(recommended_services or []),
            urgency=urgency,
            suggested_sales_action=suggested_sales_action,
            suggested_outreach_message=suggested_outreach_message,
            evidence_snippet=evidence_snippet,
            extra=extra,
            prompt_version=prompt_version,
            review_status=ReviewStatus.PENDING_REVIEW.value,
        )
        return self.add(signal)

    def set_review_status(self, signal: DetectedSignal, status: ReviewStatus) -> None:
        """Sync the denormalized review_status. Paired with an insert
        into signal_reviews by the caller inside the same transaction."""
        signal.review_status = status.value
        self.db.flush()
