from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    """Request-scoped identity derived from a verified JWT.

    `email` and `full_name` are populated from the token claims; services
    that only need tenant/user/role can keep ignoring them."""

    user_id: UUID
    tenant_id: UUID
    role: str
    email: str | None = None
    full_name: str | None = None

    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"
