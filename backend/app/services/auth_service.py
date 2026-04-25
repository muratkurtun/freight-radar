from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.domain.schemas import LoginRequest, TokenResponse
from app.repositories.tenants import TenantRepository
from app.repositories.users import UserRepository
from app.security.jwt import create_access_token
from app.security.passwords import verify_password


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def login(self, request: LoginRequest) -> TokenResponse:
        users = UserRepository(self.db)
        tenants = TenantRepository(self.db)

        user = users.get_by_email(request.email.lower())
        if user is None or not user.is_active:
            raise AuthError("Invalid email or password")
        if not verify_password(request.password, user.password_hash):
            raise AuthError("Invalid email or password")

        tenant = tenants.get(user.tenant_id)
        if tenant is None or not tenant.is_active:
            # Treat a deactivated tenant as an authentication failure so we
            # don't leak the existence of the account via a different code.
            raise AuthError("Invalid email or password")

        token = create_access_token(
            subject=str(user.id),
            tenant_id=str(user.tenant_id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            subscription_status=tenant.subscription_status,
            trial_ends_at=tenant.trial_ends_at,
        )
        users.touch_last_login(user)
        self.db.commit()
        return TokenResponse(access_token=token)
