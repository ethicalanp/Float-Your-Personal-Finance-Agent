import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.ai.gateway.adapters.base import BaseAdapter
from app.ai.gateway.capabilities import ModelCapabilities
from app.ai.gateway.errors import (
    AuthError,
    BadRequest,
    RateLimited,
    Timeout,
    TransientProviderError,
)
from app.ai.gateway.types import LLMRequest, LLMResponse, TokenUsage

logger = logging.getLogger("app.ai.gateway.adapters.openai_compatible")


def _make_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively enforce additionalProperties=False and required fields for strict OpenAI/Groq schemas."""
    import copy

    s = copy.deepcopy(schema)

    def recurse(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            if "properties" in node:
                node["required"] = list(node["properties"].keys())
                for v in node["properties"].values():
                    recurse(v)
        if "$defs" in node:
            for v in node["$defs"].values():
                recurse(v)
        if "items" in node and isinstance(node["items"], dict):
            recurse(node["items"])

    recurse(s)
    return s


class OpenAICompatibleAdapter(BaseAdapter):
    """Universal adapter for OpenAI-compatible chat completion endpoints.

    Supports Groq, OpenAI, Azure OpenAI, Together, vLLM, Ollama, etc.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self._custom_client = client is not None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        if not self._custom_client:
            await self._client.aclose()

    async def check_auth(self) -> bool:
        """Probe provider authentication endpoint without leaking secrets or throwing stack traces."""
        if not self.api_key or not self.api_key.strip():
            logger.warning("Provider API key missing or empty. Check key/env var name/quotes/whitespace.")
            raise AuthError("Provider API key missing or empty")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Float-Agent/1.0",
        }
        endpoint = f"{self.base_url}/models"
        try:
            resp = await self._client.get(endpoint, headers=headers)
            if resp.status_code in (401, 403):
                logger.warning(
                    "Provider authentication failed (%d). Check key/env var name/quotes/whitespace.",
                    resp.status_code,
                )
                raise AuthError(f"Provider authentication error ({resp.status_code})")
            return resp.is_success
        except AuthError:
            raise
        except Exception as e:
            logger.warning("Provider auth probe connection warning: %s", type(e).__name__)
            return False

    async def complete(self, request: LLMRequest, capabilities: ModelCapabilities) -> LLMResponse:
        start_time = time.monotonic()
        endpoint = f"{self.base_url}/chat/completions"

        # Headers - Never send internal user_id upstream!
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Messages formatting
        messages_payload: list[dict[str, str]] = [{"role": m.role, "content": m.content} for m in request.messages]

        max_tokens_val = request.max_output_tokens
        if "gpt-oss" in self.model.lower() and max_tokens_val < 1500:
            max_tokens_val = 1500

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages_payload,
            "temperature": request.temperature,
            "max_tokens": max_tokens_val,
        }

        # Handle structured output / schema preferences
        if request.response_schema is not None:
            raw_schema = (
                request.response_schema.model_json_schema()
                if isinstance(request.response_schema, type) and issubclass(request.response_schema, BaseModel)
                else request.response_schema
            )
            schema_dict = _make_strict_json_schema(raw_schema) if isinstance(raw_schema, dict) else raw_schema

            if capabilities.supports_json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response_format",
                        "schema": schema_dict,
                        "strict": True,
                    },
                }
            elif capabilities.supports_json_mode:
                payload["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise Timeout(f"Provider request timed out after {self.timeout}s: {exc}") from exc
        except httpx.NetworkError as exc:
            raise TransientProviderError(f"Network error contacting provider: {exc}") from exc
        except Exception as exc:
            raise TransientProviderError(f"Unexpected provider connection error: {exc}") from exc

        latency_ms = (time.monotonic() - start_time) * 1000.0

        if response.status_code == 429:
            retry_after_val: float | None = None
            retry_after_hdr = response.headers.get("Retry-After")
            if retry_after_hdr:
                try:
                    retry_after_val = float(retry_after_hdr)
                except ValueError:
                    pass
            raise RateLimited(f"Provider rate limit (429): {response.text}", retry_after=retry_after_val)

        if response.status_code in (401, 403):
            raise AuthError(f"Provider authentication error ({response.status_code})")

        if response.status_code in (400, 422):
            raise BadRequest(f"Provider rejected request ({response.status_code}): {response.text}")

        if response.status_code >= 500:
            raise TransientProviderError(f"Provider server error ({response.status_code}): {response.text}")

        if not response.is_success:
            raise TransientProviderError(f"Unexpected HTTP {response.status_code}: {response.text}")

        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "stop")
            raw_usage = data.get("usage", {})
            input_tokens = raw_usage.get("prompt_tokens", 0)
            output_tokens = raw_usage.get("completion_tokens", 0)
        except Exception as exc:
            raise TransientProviderError(f"Malformed response payload from provider: {exc}") from exc

        return LLMResponse(
            text=content or "",
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                estimated_cost_usd=0.0,
            ),
            model=self.model,
            provider="openai_compatible",
            latency_ms=latency_ms,
            retries=0,
            finish_reason=finish_reason,
        )
