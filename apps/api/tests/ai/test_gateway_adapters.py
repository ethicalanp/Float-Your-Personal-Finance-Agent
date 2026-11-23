import json

import httpx
import pytest

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.adapters.openai_compatible import OpenAICompatibleAdapter
from app.ai.gateway.capabilities import ModelCapabilities
from app.ai.gateway.types import LLMMessage, LLMRequest, LLMResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", ["fake", "openai_mock"])
async def test_adapters_satisfy_contract(adapter_type: str):
    req = LLMRequest(
        messages=[
            LLMMessage(role="system", content="You are a helpful assistant."),
            LLMMessage(role="user", content="What is financial planning?"),
        ],
        temperature=0.0,
        max_output_tokens=100,
        data_class="demo",
    )
    caps = ModelCapabilities(
        supports_json_schema=True,
        supports_json_mode=True,
        supports_tools=False,
        max_context_tokens=8192,
    )

    if adapter_type == "fake":
        adapter = FakeProvider(default_response="Financial planning is managing cash flows.")
    else:
        # Mock transport for OpenAICompatibleAdapter
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/chat/completions")
            body = json.loads(request.content)
            # Verify internal user_id is never passed in request payload
            assert "user_id" not in body
            mock_payload = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Financial planning is managing cash flows."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
            }
            return httpx.Response(200, json=mock_payload)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = OpenAICompatibleAdapter(
            base_url="https://api.openai.com/v1",
            api_key="mock-key",
            model="gpt-4o-mini",
            client=mock_client,
        )

    try:
        response = await adapter.complete(req, caps)
        assert isinstance(response, LLMResponse)
        assert "Financial planning" in response.text
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
        assert response.finish_reason == "stop"
    finally:
        await adapter.close()
