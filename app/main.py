from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import router as web_router
from app.api.api import router as api_router
from app.services.bootstrap import bootstrap_admin
from app.services.scheduler import start_scheduler


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="metrics_session",
        same_site="lax",
        https_only=(settings.environment.lower() == "production"),
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(web_router)
    app.include_router(api_router, prefix="/api")

    @app.on_event("startup")
    async def _startup() -> None:
        await bootstrap_admin()
        start_scheduler(app)

    return app


app = create_app()
