from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PermissionError(AppError):  # noqa: A001 - intentional shadow
    status_code = 403
    code = "permission_denied"


class TenantMismatchError(AppError):
    status_code = 403
    code = "tenant_mismatch"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class SubscriptionExpiredError(AppError):
    """Returned for every business endpoint when the tenant's trial has
    ended and no paid subscription is active. The frontend pattern-matches
    on `code == "trial_expired"` to render the upgrade / expired screen."""

    status_code = 403
    code = "trial_expired"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
