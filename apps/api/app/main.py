import os
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppException, format_error_response
from app.core.middleware import (
    RequestContextMiddleware,
    StatementUploadLimitMiddleware,
    setup_json_logging,
)


@asynccontextmanager
async def app_lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan handler: auto-initializes local SQLite tables in development."""
    settings_obj: Settings = app_instance.state.settings
    db_url = settings_obj.database_url
    if "sqlite" in db_url and settings_obj.app_env == "development":
        import app.models  # noqa: F401
        from app.db.session import Base, get_async_engine
        from app.models.knowledge import KnowledgeChunk
        from app.models.recurring import (  # noqa: F401
            RecurringCommitment,
            RecurringNotification,
            RecurringOccurrence,
        )

        engine = get_async_engine()
        async with engine.begin() as conn:
            sqlite_tables = [table for table in Base.metadata.sorted_tables if table is not KnowledgeChunk.__table__]
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=sqlite_tables))
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings; production uses the environment."""
    settings = settings or get_settings()

    # Configure structured JSON logging
    setup_json_logging(settings.log_level)

    # Debug tracebacks are strictly disabled unless ENV=local
    env_str = os.environ.get("ENV", settings.app_env).lower()
    is_local_env = env_str in ("local", "loc")
    effective_debug = settings.debug and is_local_env

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=effective_debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=app_lifespan,
    )
    application.state.settings = settings

    # Mount Statement Upload Limit and Request Context Middlewares
    application.add_middleware(StatementUploadLimitMiddleware)
    application.add_middleware(RequestContextMiddleware)

    # Global Exception Handlers for Unified Error Format
    @application.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=req_id,
            ),
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=format_error_response(
                code="VALIDATION_ERROR",
                message="Request payload validation failed",
                details=list(exc.errors()),
                request_id=req_id,
            ),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(
                code=code,
                message=str(exc.detail),
                request_id=req_id,
            ),
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        details: list[dict[str, str]] = []
        if is_local_env and settings.debug:
            details = [{"traceback": traceback.format_exc()}]
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
                details=details,
                request_id=req_id,
            ),
        )

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    from app.api.v1.auth import get_auth_capabilities
    from app.api.v1.health import readiness_check

    application.add_api_route("/ready", readiness_check, methods=["GET"], tags=["Health"])
    application.add_api_route(
        "/auth/capabilities",
        get_auth_capabilities,
        methods=["GET"],
        tags=["Authentication & Consent"],
    )

    # Mount static assets (logos, branding)
    from pathlib import Path

    from starlette.staticfiles import StaticFiles

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Conditionally mount SQLAdmin internal administration panel and IP allowlist middleware
    if settings.admin_enabled:
        from app.admin.middleware import AdminIPAllowlistMiddleware
        from app.admin.panel import setup_admin_panel

        application.add_middleware(
            AdminIPAllowlistMiddleware,
            allowed_ips=settings.admin_allowed_ips,
        )
        setup_admin_panel(application, settings)

    return application


app = create_app()
