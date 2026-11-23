from pydantic import BaseModel


class ModelCapabilities(BaseModel):
    supports_json_schema: bool = False
    supports_json_mode: bool = False
    supports_tools: bool = False
    max_context_tokens: int = 4096
    supports_streaming: bool = False


# Known model capability catalog
_CAPABILITIES_REGISTRY: dict[tuple[str, str], ModelCapabilities] = {
    # Groq models
    ("groq", "openai/gpt-oss-120b"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=131072,
        supports_streaming=True,
    ),
    ("groq", "openai/gpt-oss-20b"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=131072,
        supports_streaming=True,
    ),
    ("groq", "qwen/qwen3.8-27b"): ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=32768,
        supports_streaming=True,
    ),
    ("groq", "llama-3.3-70b-versatile"): ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=131072,
        supports_streaming=True,
    ),
    ("groq", "llama-3.1-8b-instant"): ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=131072,
        supports_streaming=True,
    ),
    # OpenAI models
    ("openai", "gpt-4o"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=128000,
        supports_streaming=True,
    ),
    ("openai", "gpt-4o-mini"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=128000,
        supports_streaming=True,
    ),
    # Google Gemini models
    ("google", "gemini-1.5-flash"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=1048576,
        supports_streaming=True,
    ),
    ("google", "gemini-2.0-flash"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=1048576,
        supports_streaming=True,
    ),
    # Anthropic Claude models
    ("anthropic", "claude-3-5-sonnet-20241022"): ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=200000,
        supports_streaming=True,
    ),
    ("anthropic", "claude-3-5-haiku-20241022"): ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=200000,
        supports_streaming=True,
    ),
    # Test fake provider
    ("fake", "fake-model"): ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=True,
        max_context_tokens=8192,
        supports_streaming=False,
    ),
}


def get_model_capabilities(provider: str, model: str) -> ModelCapabilities:
    """Retrieve capabilities for a (provider, model) pair.

    Unknown models get conservative defaults (no JSON schema, no tools, 4k tokens).
    """
    key = (provider.strip().lower(), model.strip().lower())
    if key in _CAPABILITIES_REGISTRY:
        return _CAPABILITIES_REGISTRY[key]

    # Conservative default for unknown models
    return ModelCapabilities(
        supports_json_schema=False,
        supports_json_mode=False,
        supports_tools=False,
        max_context_tokens=4096,
        supports_streaming=False,
    )
