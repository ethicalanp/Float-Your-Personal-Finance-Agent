from abc import ABC, abstractmethod

from app.ai.gateway.capabilities import ModelCapabilities
from app.ai.gateway.types import LLMRequest, LLMResponse


class BaseAdapter(ABC):
    """Abstract base adapter for LLM providers."""

    @abstractmethod
    async def complete(self, request: LLMRequest, capabilities: ModelCapabilities) -> LLMResponse:
        """Send completion request to LLM provider."""
        raise NotImplementedError

    async def close(self) -> None:
        """Clean up underlying HTTP clients or connections."""
        return None

    async def check_auth(self) -> bool:
        """Validate API credentials against the provider endpoint."""
        return True
