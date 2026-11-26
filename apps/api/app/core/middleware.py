import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import format_error_response

# Context variable to make request_id accessible throughout the request lifecycle
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")

MAX_STATEMENT_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_UPLOAD_ERROR_MESSAGE = "Statement content exceeds maximum allowed size of 10 MB."


class StatementUploadLimitMiddleware:
    """Enforces strict statement upload limits without buffering oversized bodies into memory:

    1. Early rejection if Content-Length header > 10 MB (413 PAYLOAD_TOO_LARGE).
    2. Capped streaming read aborting immediately once cumulative stream bytes exceed 10 MB (413 PAYLOAD_TOO_LARGE).
    """

    def __init__(self, app: Any, max_size: int = MAX_STATEMENT_UPLOAD_SIZE) -> None:
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope["type"] == "http"
            and scope.get("path", "").endswith("/upload-statement")
            and scope.get("method") == "POST"
        ):
            # 1. Early Content-Length header enforcement
            headers = dict(scope.get("headers", []))
            cl_header = headers.get(b"content-length")
            if cl_header:
                try:
                    if int(cl_header.decode("latin1")) > self.max_size:
                        req_id = request_id_ctx_var.get("")
                        response = JSONResponse(
                            status_code=413,
                            content=format_error_response(
                                code="PAYLOAD_TOO_LARGE",
                                message=MAX_UPLOAD_ERROR_MESSAGE,
                                request_id=req_id,
                            ),
                        )
                        await response(scope, receive, send)
                        return
                except (ValueError, UnicodeDecodeError):
                    pass

            # 2. Capped streaming read enforcement
            total_bytes = 0
            limit_exceeded = False
            client_disconnected = False
            response_started = False

            async def capped_receive() -> dict[str, Any]:
                nonlocal total_bytes, limit_exceeded, client_disconnected
                message = await receive()
                msg_type = message.get("type")
                if msg_type == "http.disconnect":
                    client_disconnected = True
                    return cast(dict[str, Any], message)
                if msg_type == "http.request":
                    body_chunk = message.get("body", b"")
                    total_bytes += len(body_chunk)
                    if total_bytes > self.max_size:
                        from app.core.errors import PayloadTooLargeException

                        limit_exceeded = True
                        raise PayloadTooLargeException(MAX_UPLOAD_ERROR_MESSAGE)
                return cast(dict[str, Any], message)

            async def guarded_send(message: dict[str, Any]) -> None:
                nonlocal response_started
                # Suppress FastAPI's body-parse error response when our stream cap aborted the read.
                if limit_exceeded:
                    return
                if message.get("type") == "http.response.start":
                    response_started = True
                await send(message)

            try:
                await self.app(scope, capped_receive, guarded_send)
            except Exception as exc:
                from app.core.errors import PayloadTooLargeException

                if not isinstance(exc, PayloadTooLargeException) and not limit_exceeded:
                    raise

            if limit_exceeded and not response_started and not client_disconnected:
                req_id = request_id_ctx_var.get("")
                response = JSONResponse(
                    status_code=413,
                    content=format_error_response(
                        code="PAYLOAD_TOO_LARGE",
                        message=MAX_UPLOAD_ERROR_MESSAGE,
                        request_id=req_id,
                    ),
                )
                await response(scope, receive, send)
                return

            return

        await self.app(scope, receive, send)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get(""),
        }

        # Include extra attributes if present
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_payload.update(record.extra_data)

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, ensure_ascii=False)


def setup_json_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root logger to emit structured JSON to stdout."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)
    else:
        for existing_handler in root_logger.handlers:
            existing_handler.setFormatter(JsonFormatter())

    return logging.getLogger("pfa.api")


logger = logging.getLogger("pfa.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to assign request_id and emit structured access logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Honor incoming X-Request-ID or generate a new UUID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx_var.set(req_id)
        request.state.request_id = req_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "latency_ms": latency_ms,
                "client_ip": request.client.host if request.client else None,
            }
            logger.error("Request failed with unhandled exception", extra={"extra_data": log_data})
            raise
        finally:
            request_id_ctx_var.reset(token)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = req_id

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "client_ip": request.client.host if request.client else None,
        }
        logger.info(f"{request.method} {request.url.path} {response.status_code}", extra={"extra_data": log_data})

        return response
