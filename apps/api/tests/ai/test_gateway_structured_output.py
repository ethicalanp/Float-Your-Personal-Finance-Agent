import pytest
from pydantic import BaseModel, Field

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.errors import InvalidStructuredOutput
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest


class CategoryResponse(BaseModel):
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_recurring: bool


@pytest.mark.asyncio
async def test_structured_output_valid_on_first_try():
    valid_json = '{"category": "Groceries", "confidence": 0.95, "is_recurring": false}'
    fake = FakeProvider(default_response=valid_json)
    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake)

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Categorize transaction: BigBasket ₹1,200")],
        response_schema=CategoryResponse,
        data_class="demo",
    )
    res = await gateway.complete(req)

    assert res.parsed is not None
    assert isinstance(res.parsed, CategoryResponse)
    assert res.parsed.category == "Groceries"
    assert res.parsed.confidence == 0.95
    assert res.parsed.is_recurring is False
    assert len(fake.history) == 1


@pytest.mark.asyncio
async def test_structured_output_repaired_on_second_try():
    # First response is broken JSON, second is valid JSON
    bad_json = "Here is your JSON: {category: Groceries, confidence: 'high'}"
    good_json = '{"category": "Groceries", "confidence": 0.88, "is_recurring": true}'

    fake = FakeProvider()
    fake.enqueue(bad_json)
    fake.enqueue(good_json)

    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake)

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Categorize transaction: MilkBasket ₹500")],
        response_schema=CategoryResponse,
        data_class="demo",
    )
    res = await gateway.complete(req)

    # Exactly one repair attempt was made and succeeded
    assert len(fake.history) == 2
    assert res.parsed is not None
    assert isinstance(res.parsed, CategoryResponse)
    assert res.parsed.category == "Groceries"
    assert res.parsed.confidence == 0.88
    assert res.parsed.is_recurring is True
    # The repair prompt was included in the second call
    assert "validation errors" in fake.history[1].messages[-1].content


@pytest.mark.asyncio
async def test_structured_output_fails_after_single_repair():
    # Both initial and repair response are invalid
    bad_json_1 = "Sorry, cannot parse this"
    bad_json_2 = '{"category": "Groceries", "confidence": "still invalid string"}'

    fake = FakeProvider()
    fake.enqueue(bad_json_1)
    fake.enqueue(bad_json_2)

    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake)

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Categorize: ₹500")],
        response_schema=CategoryResponse,
        data_class="demo",
    )

    with pytest.raises(InvalidStructuredOutput) as exc_info:
        await gateway.complete(req)

    assert "structured schema validation after repair attempt" in str(exc_info.value)
    # Stopped after exactly one repair attempt
    assert len(fake.history) == 2
