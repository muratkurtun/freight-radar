from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_router
from app.api import company_leads as company_leads_router
from app.api import feedback as feedback_router
from app.api import opportunities as opportunities_router
from app.api import pipeline as pipeline_router
from app.api import platform_sources as platform_sources_router
from app.api import review as review_router
from app.api import reviews as reviews_router
from app.api import signals as signals_router
from app.api import tenant_preferences as tenant_preferences_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.scheduler.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Opportunity Radar API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(auth_router.router)
    app.include_router(platform_sources_router.router)
    app.include_router(tenant_preferences_router.router)
    app.include_router(signals_router.router)
    app.include_router(review_router.router)  # legacy /review/* — preserved
    app.include_router(reviews_router.router)
    app.include_router(opportunities_router.router)
    app.include_router(company_leads_router.router)
    app.include_router(feedback_router.router)
    app.include_router(pipeline_router.trigger_router)
    app.include_router(pipeline_router.runs_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
