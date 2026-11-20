from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppException, format_error_response
from app.core.middleware import RequestContextMiddleware, setup_json_logging


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip raw user inputs from validation error details to prevent echoing passwords/secrets."""
    sanitized = []
    for err in errors:
        clean_err = dict(err)
        clean_err.pop("input", None)
        if "ctx" in clean_err and isinstance(clean_err["ctx"], dict):
            clean_ctx = dict(clean_err["ctx"])
            clean_ctx.pop("input", None)
            clean_err["ctx"] = clean_ctx
        sanitized.append(clean_err)
    return sanitized


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings; production uses the environment."""
    settings = settings or get_settings()

    # Configure structured JSON logging
    setup_json_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    application.state.settings = settings

    # Mount Request ID and Structured Access Logging Middleware
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
                details=sanitize_validation_errors(list(exc.errors())),
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
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
                request_id=req_id,
            ),
        )

    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
