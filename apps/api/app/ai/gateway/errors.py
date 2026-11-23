class LLMGatewayError(Exception):
    """Base exception for all LLM gateway errors."""

    def __init__(self, message: str = "LLM gateway error"):
        self.message = message
        super().__init__(message)


class RateLimited(LLMGatewayError):
    """Provider rate limit reached (HTTP 429)."""

    def __init__(self, message: str = "Rate limited by provider", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class TransientProviderError(LLMGatewayError):
    """Temporary provider failure (HTTP 500, 502, 503, 504, connection reset)."""


class Timeout(LLMGatewayError):
    """Request exceeded per-call or overall budget timeout."""


class AuthError(LLMGatewayError):
    """Authentication or authorization failure with provider (HTTP 401, 403)."""


class BadRequest(LLMGatewayError):
    """Malformed request or unsupported parameters (HTTP 400, 422)."""


class InvalidStructuredOutput(LLMGatewayError):
    """Model output failed schema validation even after repair attempt."""

    def __init__(
        self,
        message: str = "Invalid structured output from model",
        raw_text: str = "",
        schema_errors: list[str] | None = None,
    ):
        super().__init__(message)
        self.raw_text = raw_text
        self.schema_errors = schema_errors or []


class BudgetExceeded(LLMGatewayError):
    """Token or cost budget exceeded (request or user daily limit)."""

    def __init__(self, message: str = "Token budget exceeded", budget_type: str = "request"):
        super().__init__(message)
        self.budget_type = budget_type


class CircuitOpen(LLMGatewayError):
    """Circuit breaker is open; failing fast to protect provider and user latency."""


class ProviderNotApproved(LLMGatewayError):
    """Provider is not approved for real customer data in the current environment."""


class MaskingFailed(LLMGatewayError):
    """PII masking failed or post-mask leak scanner detected unmasked sensitive data."""


def to_user_safe_message(error: Exception) -> str:
    """Map gateway exception to safe, non-revealing user message."""
    if isinstance(error, RateLimited):
        return "The AI assistant is receiving high traffic right now. Please wait a moment and try again."
    if isinstance(error, Timeout):
        return "The request took too long to complete. Please try again."
    if isinstance(error, BudgetExceeded):
        return "You have reached your daily AI usage limit. It will reset tomorrow."
    if isinstance(error, MaskingFailed):
        return (
            "Your request could not be processed due to privacy safety checks. "
            "Please remove sensitive details and retry."
        )
    if isinstance(error, CircuitOpen | TransientProviderError):
        return (
            "The AI service is temporarily unavailable. "
            "Core Float features (Plan, Protect, Borrow) remain fully functional."
        )
    if isinstance(error, ProviderNotApproved):
        return "The AI provider is currently disabled for live data in this environment."
    return "An error occurred while communicating with the AI service. Please try again later."
