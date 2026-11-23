import asyncio
import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.gateway.adapters import create_adapter
from app.ai.gateway.adapters.base import BaseAdapter
from app.ai.gateway.budgets import BudgetStore, InMemoryBudgetStore
from app.ai.gateway.cache import ResponseCache
from app.ai.gateway.capabilities import get_model_capabilities
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.context_window import estimate_tokens
from app.ai.gateway.errors import (
    BudgetExceeded,
    InvalidStructuredOutput,
    ProviderNotApproved,
    Timeout,
    TransientProviderError,
)
from app.ai.gateway.resilience import (
    CircuitBreaker,
    calculate_backoff,
    is_retryable,
)
from app.ai.gateway.types import LLMMessage, LLMRequest, LLMResponse
from app.ai.security.leak_scanner import assert_no_leaks
from app.ai.security.tracing import log_llm_trace

logger = logging.getLogger("app.ai.gateway")


def _clean_markdown_json(text: str) -> str:
    """Extract raw JSON string if wrapped in markdown code fence."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


class LLMGateway:
    """Central gateway orchestrating LLM interactions, resilience, budgets, security, and structured output repair."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        adapter: BaseAdapter | None = None,
        fallback_adapter: BaseAdapter | None = None,
        budget_store: BudgetStore | None = None,
    ):
        self.config = config or LLMConfig()
        self.adapter = adapter or create_adapter(
            provider=self.config.provider,
            base_url=self.config.base_url,
            api_key=self.config.api_key.get_secret_value() if self.config.api_key else None,
            model=self.config.model,
            timeout=self.config.timeout_seconds,
        )

        self.fallback_adapter = fallback_adapter
        if self.fallback_adapter is None and self.config.fallback and self.config.fallback.provider:
            self.fallback_adapter = create_adapter(
                provider=self.config.fallback.provider,
                base_url=self.config.fallback.base_url,
                api_key=self.config.fallback.api_key.get_secret_value() if self.config.fallback.api_key else None,
                model=self.config.fallback.model,
                timeout=self.config.timeout_seconds,
            )

        self.budget_store = budget_store or InMemoryBudgetStore()
        self.circuit_breaker = CircuitBreaker()
        self.cache = ResponseCache()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)

    async def close(self) -> None:
        await self.adapter.close()
        if self.fallback_adapter:
            await self.fallback_adapter.close()

    async def validate_auth(self) -> bool:
        """Probe provider authentication. Returns True if valid, False/AuthError if invalid."""
        if self.config.provider.lower() == "fake":
            return True
        if hasattr(self.adapter, "check_auth"):
            return await self.adapter.check_auth()
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.monotonic()

        # 1. Privacy & Masking Verification
        if request.data_class == "masked_real":
            for msg in request.messages:
                assert_no_leaks(msg.content)

        # 2. Environment & Provider Approval Check
        if not self.config.is_provider_approved(request.data_class):
            raise ProviderNotApproved(
                f"Provider '{self.config.provider}' is not approved for data class '{request.data_class}'"
            )

        # 3. Budget checks
        est_input_tokens = sum(estimate_tokens(m.content) for m in request.messages)
        total_est = est_input_tokens + request.max_output_tokens
        if total_est > self.config.request_token_budget:
            raise BudgetExceeded(
                f"Estimated tokens ({total_est}) exceed request token budget ({self.config.request_token_budget})",
                budget_type="request",
            )

        if request.user_id:
            await self.budget_store.check_and_increment(request.user_id, 0, self.config.daily_token_budget_per_user)

        # 4. Deterministic Cache Check
        cached_resp = self.cache.get(request, self.config.model)
        if cached_resp:
            log_llm_trace(
                trace_id=request.trace_id,
                provider=cached_resp.provider,
                model=cached_resp.model,
                prompt_version=request.prompt_version,
                input_tokens=cached_resp.usage.input_tokens,
                output_tokens=cached_resp.usage.output_tokens,
                latency_ms=(time.monotonic() - start_time) * 1000.0,
                retries=0,
                validation_result="cached",
                data_class=request.data_class,
                extra={"cached": True},
            )
            return cached_resp

        # 5. Circuit Breaker Pre-call Check
        await self.circuit_breaker.before_call()

        # 6. Concurrency control with queue timeout
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=5.0)
        except asyncio.TimeoutError as exc:
            raise Timeout("LLM concurrency queue timeout exceeded") from exc

        retries_done = 0
        response: LLMResponse | None = None
        used_fallback = False
        active_provider = self.config.provider
        active_model = self.config.model

        try:
            capabilities = get_model_capabilities(self.config.provider, self.config.model)

            for attempt in range(self.config.max_retries + 1):
                # Check overall budget seconds
                elapsed = time.monotonic() - start_time
                remaining_budget = self.config.overall_budget_seconds - elapsed
                if remaining_budget <= 0:
                    raise Timeout(f"Overall LLM budget seconds ({self.config.overall_budget_seconds}s) exceeded")

                try:
                    response = await asyncio.wait_for(
                        self.adapter.complete(request, capabilities),
                        timeout=min(self.config.timeout_seconds, remaining_budget),
                    )
                    await self.circuit_breaker.record_success()
                    break
                except Exception as exc:
                    await self.circuit_breaker.record_failure(exc)

                    # If not retryable or final attempt, check fallback or re-raise
                    can_retry = is_retryable(exc) and attempt < self.config.max_retries
                    if not can_retry:
                        # Attempt failover to fallback if explicitly enabled, configured, and allowed
                        if (
                            self.config.allow_cross_provider_fallback
                            and self.fallback_adapter
                            and self.config.fallback
                            and (request.data_class == "demo" or self.config.fallback.approved_for_real_data)
                            and not used_fallback
                        ):
                            logger.warning(
                                "Failing over to fallback LLM provider '%s' due to: %s",
                                self.config.fallback.provider,
                                exc,
                            )
                            used_fallback = True
                            active_provider = self.config.fallback.provider
                            active_model = self.config.fallback.model
                            fallback_caps = get_model_capabilities(active_provider, active_model)
                            try:
                                response = await self.fallback_adapter.complete(request, fallback_caps)
                                break
                            except Exception as fb_exc:
                                raise fb_exc from exc

                        raise exc

                    # Bounded exponential backoff + jitter
                    retries_done += 1
                    retry_after = getattr(exc, "retry_after", None)
                    backoff = calculate_backoff(attempt, retry_after=retry_after)
                    await asyncio.sleep(backoff)

            if response is None:
                raise TransientProviderError("No response received from LLM provider")

        finally:
            self._semaphore.release()

        # 7. Structured Output Validation & Single Repair Attempt
        repaired = False
        if request.response_schema is not None:
            clean_text = _clean_markdown_json(response.text)
            parsed_obj: Any = None
            schema_err: Exception | None = None

            try:
                if isinstance(request.response_schema, type) and issubclass(request.response_schema, BaseModel):
                    parsed_obj = request.response_schema.model_validate_json(clean_text)
                else:
                    parsed_obj = json.loads(clean_text)
                response.parsed = parsed_obj
            except (ValidationError, json.JSONDecodeError, ValueError) as err:
                schema_err = err

            # Exactly one repair attempt if validation failed
            if schema_err is not None:
                logger.info("Structured output failed validation. Attempting single repair prompt.")
                repair_prompt = (
                    f"Your previous response had validation errors:\n{schema_err}\n\n"
                    f"Please fix the format and return strictly valid JSON matching the requested structure."
                )
                repair_messages = list(request.messages) + [
                    LLMMessage(role="assistant", content=response.text),
                    LLMMessage(role="user", content=repair_prompt),
                ]
                repair_request = LLMRequest(
                    messages=repair_messages,
                    response_schema=request.response_schema,
                    temperature=0.0,
                    max_output_tokens=request.max_output_tokens,
                    prompt_version=request.prompt_version,
                    trace_id=request.trace_id,
                    user_id=request.user_id,
                    data_class=request.data_class,
                )

                repair_response = await self.adapter.complete(repair_request, capabilities)
                clean_repair_text = _clean_markdown_json(repair_response.text)

                try:
                    if isinstance(request.response_schema, type) and issubclass(request.response_schema, BaseModel):
                        parsed_repair = request.response_schema.model_validate_json(clean_repair_text)
                    else:
                        parsed_repair = json.loads(clean_repair_text)
                    response.text = repair_response.text
                    response.parsed = parsed_repair
                    response.usage.input_tokens += repair_response.usage.input_tokens
                    response.usage.output_tokens += repair_response.usage.output_tokens
                    response.usage.total_tokens = response.usage.input_tokens + response.usage.output_tokens
                    repaired = True
                except Exception as final_err:
                    raise InvalidStructuredOutput(
                        message=f"Model output failed structured schema validation after repair attempt: {final_err}",
                        raw_text=repair_response.text,
                        schema_errors=[str(schema_err), str(final_err)],
                    ) from final_err

        # 8. Post-execution token recording in budget store
        if request.user_id:
            await self.budget_store.check_and_increment(
                request.user_id, response.usage.total_tokens, self.config.daily_token_budget_per_user
            )

        # 9. Update Cache
        self.cache.set(request, active_model, response)

        # 10. Safe trace logging
        total_latency_ms = (time.monotonic() - start_time) * 1000.0
        response.latency_ms = total_latency_ms
        response.retries = retries_done

        log_llm_trace(
            trace_id=request.trace_id,
            provider=active_provider,
            model=active_model,
            prompt_version=request.prompt_version,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=total_latency_ms,
            retries=retries_done,
            validation_result="repaired" if repaired else "success",
            data_class=request.data_class,
            extra={"repaired": repaired, "fallback_used": used_fallback},
        )

        return response
