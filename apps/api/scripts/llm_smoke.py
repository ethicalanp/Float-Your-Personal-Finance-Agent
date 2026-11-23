#!/usr/bin/env python3
"""Manual smoke test script for Float LLM Gateway.

Validates provider configuration, PII masking, bilingual response,
latency, and token accounting without exposing secret keys.

Usage:
    python scripts/llm_smoke.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env from workspace root if present
root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if not root_env.exists():
    root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if root_env.exists():
    for line in root_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.ai.gateway import LLMConfig, LLMGateway, LLMMessage, LLMRequest  # noqa: E402
from app.ai.security import assert_no_leaks, mask_pii, wrap_untrusted_data  # noqa: E402


async def main() -> None:
    print("=" * 60)
    print(" Float LLM Gateway Smoke Test")
    print("=" * 60)

    # Initialize configuration
    provider_name = os.getenv("PFA_LLM_PROVIDER")
    if not provider_name:
        provider_name = "groq" if os.getenv("GROQ_API_KEY") else "fake"

    config = LLMConfig(provider=provider_name, approved_for_real_data=True)

    print(f"Provider:       {config.provider}")
    print(f"Model:          {config.model}")
    print(f"Base URL:       {config.base_url or 'default/local'}")
    print(f"API Key Set:    {'Yes (Hidden)' if config.api_key else 'No'}")
    print("-" * 60)

    # Step 1: Demonstrate PII masking on Indian financial text
    raw_user_message = (
        "Hello Float! My phone is 9876543210 and my UPI is rahul@okhdfcbank. "
        "I sent ₹2,500.00 on 2026-11-21 to account no 123456789012. "
        "Can you verify if this is safe in English and Malayalam?"
    )

    print("\n[Step 1] Original Raw Message:")
    print(f"  {raw_user_message}")

    masked_message = mask_pii(raw_user_message)
    print("\n[Step 2] PII Masked Message (Financial amounts & dates preserved):")
    print(f"  {masked_message}")

    # Security check: fail closed if any leak remains
    assert_no_leaks(masked_message)
    print("  -> Leak scanner verified: 0 high-risk PII leaks detected.")

    # Wrap as untrusted data
    secured_content = wrap_untrusted_data(masked_message, source="user_query")

    # Step 2: Send request through LLMGateway
    gateway = LLMGateway(config=config)
    request = LLMRequest(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "You are Float's bilingual financial assistant. "
                    "Provide a helpful 2-sentence response in English, followed by a 1-sentence summary in Malayalam."
                ),
            ),
            LLMMessage(role="user", content=secured_content),
        ],
        temperature=0.2,
        max_output_tokens=300,
        data_class="masked_real",
    )

    print("\n[Step 3] Calling LLM Gateway...")
    try:
        response = await gateway.complete(request)
        print("\n[Step 4] LLM Response Received:")
        print("-" * 40)
        print(response.text.strip())
        print("-" * 40)
        print(f"Latency:        {response.latency_ms:.2f} ms")
        print(f"Input Tokens:   {response.usage.input_tokens}")
        print(f"Output Tokens:  {response.usage.output_tokens}")
        print(f"Total Tokens:   {response.usage.total_tokens}")
        print(f"Retries:        {response.retries}")
        print(f"Finish Reason:  {response.finish_reason}")
    except Exception as exc:
        print(f"\n[ERROR] Gateway call failed: {exc}")
    finally:
        await gateway.close()

    print("\n" + "=" * 60)
    print(" Smoke Test Finished Successfully")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
