import asyncio
import time

from app.ai.gateway.adapters.base import BaseAdapter
from app.ai.gateway.capabilities import ModelCapabilities
from app.ai.gateway.types import LLMRequest, LLMResponse, TokenUsage


class FakeProvider(BaseAdapter):
    """Scriptable fake provider for deterministic testing of gateway resilience and workflows."""

    def __init__(self, default_response: str = "Fake assistant response"):
        self.default_response = default_response
        self._queue: list[str | LLMResponse | Exception] = []
        self.history: list[LLMRequest] = []
        self.delay: float = 0.0

    def enqueue(self, item: str | LLMResponse | Exception) -> None:
        """Enqueue a response string, full LLMResponse, or Exception to be returned on next call."""
        self._queue.append(item)

    def enqueue_sequence(self, items: list[str | LLMResponse | Exception]) -> None:
        """Enqueue multiple responses or exceptions in sequence."""
        self._queue.extend(items)

    def clear(self) -> None:
        """Reset history and queue."""
        self._queue.clear()
        self.history.clear()

    async def complete(self, request: LLMRequest, capabilities: ModelCapabilities) -> LLMResponse:
        start_time = time.monotonic()
        self.history.append(request)

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self._queue:
            item = self._queue.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, LLMResponse):
                return item
            text_response = str(item)
        else:
            text_response = self.default_response

        latency_ms = (time.monotonic() - start_time) * 1000.0

        # Estimate simple token usage for testing
        input_tokens = sum(len(m.content) // 4 for m in request.messages) + 10
        output_tokens = len(text_response) // 4 + 5

        return LLMResponse(
            text=text_response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                estimated_cost_usd=0.0,
            ),
            model="fake-model",
            provider="fake",
            latency_ms=latency_ms,
            retries=0,
            finish_reason="stop",
        )
