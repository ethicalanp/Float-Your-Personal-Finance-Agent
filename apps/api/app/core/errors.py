from typing import Any


class AppException(Exception):
    """Base application exception with standardized attributes."""

    def __init__(
        self,
        message: str,
        code: str = "APPLICATION_ERROR",
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="NOT_FOUND", status_code=404, details=details)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Authentication required", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="UNAUTHORIZED", status_code=401, details=details)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Access forbidden", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="FORBIDDEN", status_code=403, details=details)


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="BAD_REQUEST", status_code=400, details=details)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="CONFLICT", status_code=409, details=details)


class UnprocessableException(AppException):
    def __init__(self, message: str = "Unprocessable entity", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message=message, code="UNPROCESSABLE_ENTITY", status_code=422, details=details)


class ServiceUnavailableException(AppException):
    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(message=message, code="SERVICE_UNAVAILABLE", status_code=503)


def format_error_response(
    code: str,
    message: str,
    details: list[Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a single unified error JSON shape."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id or "",
        }
    }
