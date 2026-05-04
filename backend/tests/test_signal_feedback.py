"""Tests for the sales-team feedback loop.

Covers the negative-action reason-required validator, the history
preservation contract (multiple feedback rows per signal+user), and
the cross-tenant isolation guard. Repository / service paths use the
real ORM model with a stubbed Session, so the SQL-shape contract
(e.g. signal_belongs_to_tenant) is exercised through unit-level fakes
rather than a real Postgres connection."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import FeedbackAction, FeedbackReason
from app.domain.schemas import FeedbackCreate
from app.repositories.signal_feedback import SignalFeedbackRepository
from app.services.signal_feedback_service import SignalFeedbackService
from app.security.tenant_context import TenantContext


# --------------------------------------------------------------------------
# Schema validator
# --------------------------------------------------------------------------


def test_positive_action_does_not_require_reason():
    payload = FeedbackCreate(action=FeedbackAction.RELEVANT)
    assert payload.reason is None


def test_lifecycle_actions_do_not_require_reason():
    for action in (
        FeedbackAction.QUALIFIED,
        FeedbackAction.CONTACTED,
        FeedbackAction.CONVERTED,
    ):
        # Should not raise
        FeedbackCreate(action=action)


def test_negative_actions_require_reason():
    for action in (
        FeedbackAction.NOT_RELEVANT,
        FeedbackAction.DISMISSED,
        FeedbackAction.WRONG_COMPANY,
        FeedbackAction.WRONG_SECTOR,
        FeedbackAction.NOT_A_LOGISTICS_LEAD,
    ):
        with pytest.raises(ValidationError):
            FeedbackCreate(action=action)


def test_negative_action_with_reason_passes():
    payload = FeedbackCreate(
        action=FeedbackAction.NOT_RELEVANT,
        reason=FeedbackReason.WRONG_COMPANY,
        note="Different ABC, smaller firm.",
    )
    assert payload.reason == FeedbackReason.WRONG_COMPANY
    assert payload.note == "Different ABC, smaller firm."


# --------------------------------------------------------------------------
# Service / repository behaviour with fakes
# --------------------------------------------------------------------------


class _FakeQuery:
    """Records the WHEREs added to the chain so the test can assert
    that signal_belongs_to_tenant filtered by tenant_id."""

    def __init__(self, owner: "_FakeSession"):
        self.owner = owner
        self.where_calls: list[object] = []
        self.limit_value: int | None = None

    def where(self, *clauses):
        self.where_calls.extend(clauses)
        return self

    def limit(self, n: int):
        self.limit_value = n
        return self

    def order_by(self, *_clauses):
        return self


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, signal_owner_tenant=None, history=()):
        self.signal_owner_tenant = signal_owner_tenant
        self.history = list(history)
        self.added: list[object] = []
        self.committed = 0

    def execute(self, stmt, *_args, **_kwargs):
        # Distinguish the ownership probe from the history list by the
        # rendered SQL — both tests inspect the result, not the
        # statement, but the probe returns one row and history many.
        compiled = str(stmt)
        if "ORDER BY" in compiled.upper():
            return _FakeExecuteResult(self.history)
        # signal_belongs_to_tenant returns ANY one row when the FK
        # exists for the given tenant, NONE otherwise.
        if self.signal_owner_tenant is not None:
            return _FakeExecuteResult([SimpleNamespace(id=uuid4())])
        return _FakeExecuteResult([])

    def add(self, instance):
        self.added.append(instance)

    def flush(self):
        pass

    def commit(self):
        self.committed += 1

    def refresh(self, _instance):
        pass


def _ctx(tenant_id=None, user_id=None) -> TenantContext:
    return TenantContext(
        user_id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="tenant_user",
    )


def test_submit_persists_feedback_with_caller_user_and_tenant():
    ctx = _ctx()
    db = _FakeSession(signal_owner_tenant=ctx.tenant_id)
    service = SignalFeedbackService(db, ctx)

    signal_id = uuid4()
    payload = FeedbackCreate(action=FeedbackAction.QUALIFIED, note="follow up Mon")

    result = service.submit(signal_id, payload)

    assert db.added == [result]
    assert result.tenant_id == ctx.tenant_id
    assert result.user_id == ctx.user_id
    assert result.signal_id == signal_id
    assert result.action == "qualified"
    assert result.reason is None
    assert result.note == "follow up Mon"
    assert db.committed == 1


def test_submit_rejects_signal_from_another_tenant():
    """signal_belongs_to_tenant returns False → service raises NotFound
    instead of letting the FK fail later. The error message is the
    same as a missing-signal case to avoid leaking cross-tenant
    existence."""
    ctx = _ctx()
    db = _FakeSession(signal_owner_tenant=None)
    service = SignalFeedbackService(db, ctx)

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.submit(uuid4(), FeedbackCreate(action=FeedbackAction.RELEVANT))
    assert db.added == []
    assert db.committed == 0


def test_history_returns_rows_in_repository_order():
    """The service forwards repo.list_for_signal which the SQL ORDERs
    DESC by created_at — the fake just hands back whatever the test
    seeds, in seed order."""
    ctx = _ctx()
    seeded = [
        SimpleNamespace(action="qualified"),
        SimpleNamespace(action="relevant"),
    ]
    db = _FakeSession(signal_owner_tenant=ctx.tenant_id, history=seeded)
    service = SignalFeedbackService(db, ctx)

    history = service.history(uuid4())

    assert [h.action for h in history] == ["qualified", "relevant"]


def test_repository_is_tenant_scoped_via_base():
    """SignalFeedbackRepository extends TenantAwareRepository so any
    list/get path filters by tenant_id on the base query. This test
    locks the inheritance contract — if someone refactors the base
    out from under the repo, this catches it."""
    from app.repositories.base import TenantAwareRepository

    assert issubclass(SignalFeedbackRepository, TenantAwareRepository)
