import asyncio
import logging
import random
import time
from enum import Enum

from app.ai.gateway.errors import (
    AuthError,
    BadRequest,
    BudgetExceeded,
    CircuitOpen,
    InvalidStructuredOutput,
    MaskingFailed,
    ProviderNotApproved,
    RateLimited,
    Timeout,
    TransientProviderError,
)

logger = logging.getLogger("app.ai.gateway.resilience")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Circuit breaker for LLM gateway to prevent cascading provider failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    async def before_call(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning OPEN -> HALF_OPEN (probing)")
                else:
                    raise CircuitOpen("Circuit breaker is OPEN. Fast-failing LLM request.")

    async def record_success(self) -> None:
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit breaker probe succeeded. Transitioning to CLOSED.")
            self.failure_count = 0
            self.state = CircuitState.CLOSED

    async def record_failure(self, error: Exception) -> None:
        async with self._lock:
            # Only count transient provider errors & timeouts towards circuit breaking
            if isinstance(error, TransientProviderError | Timeout | RateLimited):
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker tripped OPEN after %d consecutive failures",
                        self.failure_count,
                    )


def is_retryable(error: Exception) -> bool:
    """Determine whether an error is eligible for retry."""
    # Retrying on RateLimited, TransientProviderError, or Timeout only
    if isinstance(error, RateLimited | TransientProviderError | Timeout):
        return True
    # Non-retryable errors
    if isinstance(
        error,
        AuthError
        | BadRequest
        | InvalidStructuredOutput
        | BudgetExceeded
        | CircuitOpen
        | ProviderNotApproved
        | MaskingFailed,
    ):
        return False
    return False


def calculate_backoff(
    attempt: int,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    retry_after: float | None = None,
) -> float:
    """Calculate bounded exponential backoff with full jitter, honouring Retry-After."""
    if retry_after is not None and retry_after > 0:
        # Honour provider Retry-After directly up to 60.0s
        return float(min(60.0, max(base_delay, retry_after)))

    exponential = min(max_delay, base_delay * (2**attempt))
    # Full jitter: uniform random delay between 0.5 and 1.0 * exponential
    jittered = float(exponential * random.uniform(0.5, 1.0))
    return float(min(max_delay, jittered))
