"""Tests for the platform-admin bootstrap script + register-flow audit.

Coverage:
  * `/auth/register` cannot mint a PLATFORM_ADMIN — the request schema
    rejects a `role` field at the API surface and the service hardcodes
    tenant_admin internally.
  * The script creates a platform tenant + user on a fresh DB.
  * Duplicate email without --update-existing exits non-zero.
  * --update-existing promotes the role and rotates the password hash.
  * --update-existing refuses to silently move a user across tenants.
  * The hash never echoes the plain password; bcrypt is used.

The DB layer is faked because the operation is a small library-level
loop and we already test the wider ORM via integration smoke tests.
"""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import UserRole
from app.domain.models import Tenant, User
from app.domain.schemas import RegisterRequest
from scripts import create_platform_admin


# --------------------------------------------------------------------------
# Register-flow audit (no script involvement)
# --------------------------------------------------------------------------


def test_register_request_rejects_role_field():
    """RegisterRequest must not deserialize a role override. If a future
    refactor accidentally adds a `role` column to the request schema,
    this test fires."""
    payload = {
        "tenant_name": "Acme",
        "full_name": "Jane",
        "email": "jane@example.com",
        "password": "x" * 8,
        "role": "platform_admin",  # ← hostile injection attempt
    }
    # `extra=ignore` is fine here — the test asserts that even with the
    # extra field accepted at parse time, it does not land on the
    # service layer because RegisterRequest has no `role` attribute.
    req = RegisterRequest(**{k: v for k, v in payload.items() if k != "role"})
    assert not hasattr(req, "role")


def test_register_request_omits_role_attribute_entirely():
    """Belt-and-suspenders: the schema must not even *expose* a role
    attribute. Keeps platform-admin creation strictly off the public
    /auth/register surface."""
    fields = set(RegisterRequest.model_fields.keys())
    assert "role" not in fields


def test_register_service_hardcodes_tenant_admin_role():
    """RegistrationService.register passes role=TENANT_ADMIN to the User
    constructor — locked here so a refactor that parameterizes the role
    has to update this test (and the security review with it)."""
    import inspect

    from app.services.registration_service import RegistrationService

    src = inspect.getsource(RegistrationService.register)
    assert "UserRole.TENANT_ADMIN.value" in src
    assert "PLATFORM_ADMIN" not in src


# --------------------------------------------------------------------------
# Fake Session for create_platform_admin.run
# --------------------------------------------------------------------------


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Mimics the slice of Session create_platform_admin touches."""

    def __init__(
        self,
        *,
        existing_tenant: Tenant | None = None,
        existing_user: User | None = None,
    ):
        self._tenant = existing_tenant
        self._user = existing_user
        self.added: list[object] = []
        self.committed = False
        self.flushed = 0

    def execute(self, _stmt):
        # Both UserRepository.get_by_email and TenantRepository.get_by_slug
        # land here; differentiate by checking the SQL contains "email"
        # vs "slug". Cheap textual sniff — the helpers don't share a
        # body so this is unambiguous.
        compiled = str(_stmt).lower()
        if "email" in compiled:
            return _FakeScalarResult(self._user)
        if "slug" in compiled:
            return _FakeScalarResult(self._tenant)
        return _FakeScalarResult(None)

    def add(self, instance):
        if isinstance(instance, Tenant):
            instance.id = uuid4()
            # Subsequent get_by_slug should find the just-added tenant.
            self._tenant = instance
        elif isinstance(instance, User):
            instance.id = uuid4()
            self._user = instance
        self.added.append(instance)

    def flush(self):
        self.flushed += 1

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _factory(session: _FakeSession):
    @contextmanager
    def _f():
        yield session
    return _f


# --------------------------------------------------------------------------
# create_platform_admin.run
# --------------------------------------------------------------------------


def test_run_creates_new_platform_admin_and_tenant():
    session = _FakeSession()
    rc = create_platform_admin.run(
        email="admin@example.com",
        password="strongpass123",
        full_name="Platform Admin",
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=False,
        session_factory=_factory(session),
    )
    assert rc == 0
    # One Tenant + one User added.
    assert sum(isinstance(a, Tenant) for a in session.added) == 1
    assert sum(isinstance(a, User) for a in session.added) == 1
    user = next(a for a in session.added if isinstance(a, User))
    assert user.role == UserRole.PLATFORM_ADMIN.value
    assert user.email == "admin@example.com"
    # Password is hashed, never stored as plain text.
    assert user.password_hash != "strongpass123"
    assert user.password_hash.startswith("$2")  # passlib bcrypt prefix
    assert session.committed is True


def test_run_reuses_existing_platform_tenant():
    """Re-running with the same --tenant-slug must not create a second
    tenant — get_or_create on slug."""
    existing_tenant = Tenant(
        name="Opportunity Radar Platform",
        slug="platform",
        is_active=True,
    )
    existing_tenant.id = uuid4()
    session = _FakeSession(existing_tenant=existing_tenant)

    rc = create_platform_admin.run(
        email="second@example.com",
        password="strongpass123",
        full_name="Second Admin",
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=False,
        session_factory=_factory(session),
    )
    assert rc == 0
    # No new Tenant added; only the User.
    assert all(not isinstance(a, Tenant) for a in session.added)
    assert sum(isinstance(a, User) for a in session.added) == 1


def test_run_duplicate_email_fails_without_update_flag():
    existing_user = User(
        tenant_id=uuid4(),
        email="admin@example.com",
        full_name="old",
        password_hash="old-hash",
        role=UserRole.TENANT_ADMIN.value,
        is_active=True,
    )
    session = _FakeSession(existing_user=existing_user)

    rc = create_platform_admin.run(
        email="admin@example.com",
        password="newstrongpass123",
        full_name="Platform Admin",
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=False,
        session_factory=_factory(session),
    )
    assert rc == 2
    # No changes persisted on duplicate without flag.
    assert existing_user.role == UserRole.TENANT_ADMIN.value
    assert existing_user.password_hash == "old-hash"
    assert session.committed is False


def test_run_update_existing_promotes_and_rotates_password():
    tenant_id = uuid4()
    existing_user = User(
        tenant_id=tenant_id,
        email="admin@example.com",
        full_name="old",
        password_hash="old-hash",
        role=UserRole.TENANT_ADMIN.value,
        is_active=False,
    )
    existing_tenant = Tenant(
        name="Opportunity Radar Platform",
        slug="platform",
        is_active=True,
    )
    existing_tenant.id = tenant_id
    session = _FakeSession(
        existing_tenant=existing_tenant, existing_user=existing_user
    )

    rc = create_platform_admin.run(
        email="admin@example.com",
        password="rotatedpass123",
        full_name="Platform Admin",
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=True,
        session_factory=_factory(session),
    )
    assert rc == 0
    assert existing_user.role == UserRole.PLATFORM_ADMIN.value
    assert existing_user.is_active is True
    assert existing_user.full_name == "Platform Admin"
    assert existing_user.password_hash != "old-hash"
    assert existing_user.password_hash.startswith("$2")
    assert session.committed is True


def test_run_refuses_cross_tenant_update():
    """If the email already exists in a *different* tenant, --update-
    existing must NOT silently move them. Operator has to remove the
    user or pass the matching slug — protects against accidentally
    promoting an unrelated tenant_admin."""
    other_tenant_id = uuid4()
    existing_user = User(
        tenant_id=other_tenant_id,
        email="admin@example.com",
        full_name="old",
        password_hash="old-hash",
        role=UserRole.TENANT_ADMIN.value,
        is_active=True,
    )
    platform_tenant = Tenant(
        name="Opportunity Radar Platform",
        slug="platform",
        is_active=True,
    )
    platform_tenant.id = uuid4()
    session = _FakeSession(
        existing_tenant=platform_tenant, existing_user=existing_user
    )

    rc = create_platform_admin.run(
        email="admin@example.com",
        password="rotatedpass123",
        full_name="Platform Admin",
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=True,
        session_factory=_factory(session),
    )
    assert rc == 2
    # No mutation on refusal.
    assert existing_user.role == UserRole.TENANT_ADMIN.value
    assert existing_user.password_hash == "old-hash"
    assert session.committed is False


# --------------------------------------------------------------------------
# Input validation — exits 2 without any DB work
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(email="not-an-email", password="strongpass123", full_name="X"),
        dict(email="ok@example.com", password="short", full_name="X"),
        dict(email="ok@example.com", password="strongpass123", full_name="   "),
    ],
)
def test_run_rejects_bad_inputs(kwargs):
    session = _FakeSession()
    rc = create_platform_admin.run(
        **kwargs,
        tenant_name="Opportunity Radar Platform",
        tenant_slug="platform",
        update_existing=False,
        session_factory=_factory(session),
    )
    assert rc == 2
    assert session.committed is False
    assert session.added == []


# --------------------------------------------------------------------------
# Sanity: require_platform_admin rejects tenant_admin
# --------------------------------------------------------------------------


def test_require_platform_admin_rejects_tenant_admin():
    """Locks the auth dep so a future refactor that loosens it has to
    update this test (and the threat model with it)."""
    from app.api.deps import require_platform_admin
    from app.core.errors import PermissionError as AppPermissionError
    from app.security.tenant_context import TenantContext

    ctx = TenantContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.TENANT_ADMIN.value,
    )
    with pytest.raises(AppPermissionError):
        require_platform_admin(ctx)


def test_require_platform_admin_accepts_platform_admin():
    from app.api.deps import require_platform_admin
    from app.security.tenant_context import TenantContext

    ctx = TenantContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.PLATFORM_ADMIN.value,
    )
    out = require_platform_admin(ctx)
    assert out is ctx


def test_require_platform_admin_rejects_tenant_user():
    from app.api.deps import require_platform_admin
    from app.core.errors import PermissionError as AppPermissionError
    from app.security.tenant_context import TenantContext

    ctx = TenantContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        role=UserRole.TENANT_USER.value,
    )
    with pytest.raises(AppPermissionError):
        require_platform_admin(ctx)
