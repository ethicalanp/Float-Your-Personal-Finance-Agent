import pytest
from pydantic import SecretStr

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import FallbackLLMConfig, LLMConfig
from app.ai.gateway.errors import ProviderNotApproved, TransientProviderError
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest


def test_api_key_never_leaked_in_repr_or_str():
    secret_val = "secret-super-key-9999"
    config = LLMConfig(
        provider="groq",
        api_key=SecretStr(secret_val),
        fallback=FallbackLLMConfig(
            provider="openai",
            api_key=SecretStr("fallback-secret-8888"),
        ),
    )

    repr_str = repr(config)
    str_val = str(config)
    fallback_repr = repr(config.fallback)

    # Prove raw secret keys are completely absent from representation strings
    assert secret_val not in repr_str
    assert secret_val not in str_val
    assert "fallback-secret-8888" not in fallback_repr
    assert "fallback-secret-8888" not in repr_str


@pytest.mark.asyncio
async def test_refuse_real_data_when_provider_not_approved():
    fake = FakeProvider()
    config = LLMConfig(provider="fake", approved_for_real_data=False)
    gateway = LLMGateway(config=config, adapter=fake)

    # Demo request succeeds
    demo_req = LLMRequest(
        messages=[LLMMessage(role="user", content="Hello demo")],
        data_class="demo",
    )
    demo_res = await gateway.complete(demo_req)
    assert demo_res.text is not None

    # Masked real data request is refused with ProviderNotApproved
    real_req = LLMRequest(
        messages=[LLMMessage(role="user", content="Real masked transaction")],
        data_class="masked_real",
    )
    with pytest.raises(ProviderNotApproved):
        await gateway.complete(real_req)

    # Provider was never called for real data
    assert len(fake.history) == 1


@pytest.mark.asyncio
async def test_fallback_provider_failover():
    primary_fake = FakeProvider()
    primary_fake.enqueue(TransientProviderError("Primary down"))

    fallback_fake = FakeProvider(default_response="Fallback response")

    config = LLMConfig(
        provider="fake",
        max_retries=0,
        approved_for_real_data=True,
        allow_cross_provider_fallback=True,
        fallback=FallbackLLMConfig(
            provider="fake-fallback",
            approved_for_real_data=True,
        ),
    )

    gateway = LLMGateway(
        config=config,
        adapter=primary_fake,
        fallback_adapter=fallback_fake,
    )

    req = LLMRequest(
        messages=[LLMMessage(role="user", content="Hi")],
        data_class="demo",
    )
    res = await gateway.complete(req)

    assert res.text == "Fallback response"
    assert len(primary_fake.history) == 1
    assert len(fallback_fake.history) == 1
