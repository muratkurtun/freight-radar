from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.domain.schemas import (
    CurrentUser,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.services.registration_service import RegistrationService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(db_session)) -> RegisterResponse:
    """Public self-serve registration.

    Creates a fresh tenant in TRIAL mode, makes the registrant the
    tenant admin, and returns a usable access token so the frontend can
    go straight into the trial-welcome screen without a second login."""
    return RegistrationService(db).register(payload)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(db_session)) -> TokenResponse:
    return AuthService(db).login(request)


@router.get("/me", response_model=CurrentUser)
def me(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Live view of the session — effective subscription_status is
    derived from the tenant's trial_ends_at, not cached from the JWT."""
    return current
