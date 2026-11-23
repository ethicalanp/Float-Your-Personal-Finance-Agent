import logging
from typing import Any

# Never log raw prompts, LLM answers, or unmasked financial texts
SAFE_TRACE_LOGGER = logging.getLogger("app.ai.trace")


def log_llm_trace(
    *,
    trace_id: str,
    provider: str,
    model: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    retries: int = 0,
    validation_result: str = "success",
    data_class: str = "masked_real",
    error_type: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log strictly sanitized metadata for an LLM interaction.

    Guarantees that raw user messages, completions, financial figures,
    or secret keys are NEVER written to logs.
    """
    trace_data: dict[str, Any] = {
        "event": "llm_call",
        "trace_id": trace_id,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": round(latency_ms, 2),
        "retries": retries,
        "validation_result": validation_result,
        "data_class": data_class,
    }
    if error_type:
        trace_data["error_type"] = error_type
    if extra:
        # Only allow primitive, safe telemetry keys
        safe_keys = {"cached", "repaired", "fallback_used"}
        for k, v in extra.items():
            if k in safe_keys:
                trace_data[k] = v

    SAFE_TRACE_LOGGER.info("LLM interaction trace", extra={"trace_data": trace_data})
