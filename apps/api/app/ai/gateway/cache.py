import hashlib
import json
import time
from typing import Any

from app.ai.gateway.types import LLMRequest, LLMResponse


class ResponseCache:
    """In-memory TTL cache for deterministic LLM responses (temperature == 0.0)."""

    def __init__(self, max_size: int = 500, ttl_seconds: float = 3600.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, LLMResponse]] = {}

    def _compute_key(self, request: LLMRequest, model: str) -> str:
        # Create deterministic digest based on model, prompt_version, temperature, and messages
        components: list[Any] = [
            model,
            request.prompt_version,
            request.temperature,
            [(m.role, m.content) for m in request.messages],
        ]
        serialized = json.dumps(components, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, request: LLMRequest, model: str) -> LLMResponse | None:
        # Only cache deterministic calls
        if request.temperature > 0.05:
            return None

        key = self._compute_key(request, model)
        entry = self._cache.get(key)
        if not entry:
            return None

        timestamp, response = entry
        if time.monotonic() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None

        return response

    def set(self, request: LLMRequest, model: str, response: LLMResponse) -> None:
        if request.temperature > 0.05:
            return

        if len(self._cache) >= self.max_size:
            # Simple eviction of oldest item
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

        key = self._compute_key(request, model)
        self._cache[key] = (time.monotonic(), response)

    def clear(self) -> None:
        self._cache.clear()
