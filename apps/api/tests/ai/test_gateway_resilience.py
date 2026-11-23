import asyncio

import pytest

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.errors import (
    AuthError,
    BadRequest,
    BudgetExceeded,
    CircuitOpen,
    RateLimited,
    Timeout,
    TransientProviderError,
)
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.resilience import CircuitBreaker, CircuitState, calculate_backoff, is_retryable
from app.ai.gateway.types import LLMMessage, LLMRequest


def test_is_retryable_matrix():
    assert is_retryable(RateLimited()) is True
    assert is_retryable(TransientProviderError()) is True
    assert is_retryable(Timeout()) is True

    assert is_retryable(AuthError()) is False
    assert is_retryable(BadRequest()) is False
    assert is_retryable(BudgetExceeded()) is False
    assert is_retryable(CircuitOpen()) is False


def test_calculate_backoff_and_retry_after():
    # Honoring Retry-After header
    backoff = calculate_backoff(attempt=1, retry_after=3.5)
    assert backoff == 3.5

    # Exponential jittered backoff bounds
    b0 = calculate_backoff(attempt=0, base_delay=0.5, max_delay=5.0)
    assert 0.25 <= b0 <= 0.5
    b2 = calculate_backoff(attempt=2, base_delay=0.5, max_delay=5.0)
    assert 1.0 <= b2 <= 2.0


@pytest.mark.asyncio
async def test_retry_on_429_and_500_success():
    fake = FakeProvider()
    fake.enqueue(RateLimited("Rate limited", retry_after=0.01))
    fake.enqueue(TransientProviderError("502 Bad Gateway"))
    fake.enqueue("Successful after retries")

    config = LLMConfig(provider="fake", max_retries=3, approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake)

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Hello")],
        data_class="demo",
    )
    res = await gateway.complete(req)

    assert res.text == "Successful after retries"
    assert res.retries == 2
    assert len(fake.history) == 3


@pytest.mark.asyncio
async def test_non_retryable_errors_fail_fast():
    fake = FakeProvider()
    fake.enqueue(AuthError("Invalid API key"))

    config = LLMConfig(provider="fake", max_retries=3, approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake)

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Test")],
        data_class="demo",
    )
    with pytest.raises(AuthError):
        await gateway.complete(req)

    # Failed fast: only 1 attempt
    assert len(fake.history) == 1


@pytest.mark.asyncio
async def test_circuit_breaker_trip_and_fast_fail():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
    assert cb.state == CircuitState.CLOSED

    # Record 3 failures
    await cb.record_failure(TransientProviderError("500"))
    await cb.record_failure(TransientProviderError("500"))
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure(TransientProviderError("500"))
    assert cb.state == CircuitState.OPEN

    # When OPEN, before_call raises CircuitOpen immediately
    with pytest.raises(CircuitOpen):
        await cb.before_call()

    # Wait for recovery timeout -> transitions to HALF_OPEN
    await asyncio.sleep(0.25)
    await cb.before_call()
    assert cb.state == CircuitState.HALF_OPEN

    # Probe success resets to CLOSED
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_user_daily_token_budget_enforced():
    fake = FakeProvider(default_response="Short response")
    config = LLMConfig(
        provider="fake",
        daily_token_budget_per_user=100,
        approved_for_real_data=True,
    )
    gateway = LLMGateway(config=config, adapter=fake)

    req1 = LLMRequest(
        messages=[LLMMessage(role="user", content="Message 1")],
        user_id="user_123",
        data_class="demo",
    )
    # First request consumes ~20 tokens
    res1 = await gateway.complete(req1)
    assert res1.text == "Short response"

    # Advance budget close to limit (20 + 75 = 95 <= 100)
    await gateway.budget_store.check_and_increment("user_123", 75, config.daily_token_budget_per_user)

    # Next request must be rejected with BudgetExceeded
    req2 = LLMRequest(
        messages=[LLMMessage(role="user", content="Message 2")],
        user_id="user_123",
        data_class="demo",
    )
    with pytest.raises(BudgetExceeded):
        await gateway.complete(req2)
