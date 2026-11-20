import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable to make request_id accessible throughout the request lifecycle
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")
VALID_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx_var.get("")
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": req_id,
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

    # Replace existing handlers with JSON formatter
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
    """Middleware to assign sanitized request_id and emit structured access logs with tracebacks."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Validate and bound incoming X-Request-ID to prevent memory exhaustion or header injection
        incoming_id = request.headers.get("X-Request-ID", "").strip()
        if incoming_id and VALID_REQUEST_ID_REGEX.match(incoming_id):
            req_id = incoming_id
        else:
            req_id = str(uuid.uuid4())

        token = request_id_ctx_var.set(req_id)
        request.state.request_id = req_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = req_id

            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "client_ip": request.client.host if request.client else None,
            }
            logger.info(
                f"{request.method} {request.url.path} {response.status_code}",
                extra={"extra_data": log_data},
            )
            return response

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "latency_ms": latency_ms,
                "client_ip": request.client.host if request.client else None,
            }
            # Always log complete traceback for unhandled exceptions
            logger.error(
                f"Unhandled exception during {request.method} {request.url.path}: {exc}",
                exc_info=True,
                extra={"extra_data": log_data},
            )
            raise
        finally:
            # Reset context variable only after logging is complete
            request_id_ctx_var.reset(token)
