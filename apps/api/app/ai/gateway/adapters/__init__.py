import httpx

from app.ai.gateway.adapters.base import BaseAdapter
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.adapters.openai_compatible import OpenAICompatibleAdapter


def create_adapter(
    provider: str,
    base_url: str,
    api_key: str | None,
    model: str,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
) -> BaseAdapter:
    """Create appropriate LLM adapter based on provider name."""
    provider_clean = provider.strip().lower()

    if provider_clean == "fake":
        return FakeProvider()

    if provider_clean in ("groq", "openai", "openai_compatible", "azure", "vllm", "together"):
        return OpenAICompatibleAdapter(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            client=client,
        )

    # Extension stubs for native Anthropic or Google Gemini SDKs
    if provider_clean == "anthropic":
        # Can be implemented with anthropic async client when added
        raise NotImplementedError("Native Anthropic adapter stub; use OpenAI-compatible proxy or add anthropic client.")

    if provider_clean == "gemini":
        # Can be implemented with google-genai when added
        msg = "Native Gemini adapter stub; use OpenAI-compatible endpoint or add google-genai client."
        raise NotImplementedError(msg)

    raise ValueError(f"Unsupported LLM provider: {provider}")


__all__ = ["BaseAdapter", "FakeProvider", "OpenAICompatibleAdapter", "create_adapter"]
