from app.ai.gateway.manager import LLMGateway

_gateway_instance: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    """Get the singleton LLMGateway instance."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = LLMGateway()
    return _gateway_instance


def set_llm_gateway(gateway: LLMGateway | None) -> None:
    """Override the singleton LLMGateway instance (useful for testing)."""
    global _gateway_instance
    _gateway_instance = gateway
