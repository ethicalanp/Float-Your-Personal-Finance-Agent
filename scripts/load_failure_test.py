"""Local load and failure-injection runner for Float API.

Strictly targets local PostgreSQL (localhost:5432) via in-process ASGI transport.
Never touches any non-local database.
"""

import asyncio
import math
import os
import statistics
import time
import tracemalloc
import uuid
from typing import Any

os.environ.setdefault("ENV", "local")
os.environ.setdefault("PFA_APP_ENV", "development")
os.environ.setdefault("PFA_AI_PROVIDER", "fake")
os.environ.setdefault("PFA_LLM_PROVIDER", "fake")
os.environ.setdefault(
    "PFA_DATABASE_URL",
    "postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float",
)

import httpx
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import set_llm_gateway
from app.ai.gateway.errors import RateLimited
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.dependencies import set_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.db.session import get_async_engine, get_db
from app.main import app


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, math.ceil((p / 100.0) * len(s)) - 1))
    return round(s[idx], 2)


def _summarize(name: str, latencies_ms: list[float], errors: int, elapsed_s: float, sql_count: int) -> dict[str, Any]:
    total = len(latencies_ms)
    rps = round(total / elapsed_s, 2) if elapsed_s > 0 else 0.0
    err_rate = round((errors / total) * 100, 2) if total else 0.0
    return {
        "scenario": name,
        "requests": total,
        "errors": errors,
        "error_rate_pct": err_rate,
        "rps": rps,
        "p50_ms": _pct(latencies_ms, 50),
        "p95_ms": _pct(latencies_ms, 95),
        "p99_ms": _pct(latencies_ms, 99),
        "mean_ms": round(statistics.mean(latencies_ms), 2) if latencies_ms else 0.0,
        "sql_queries_total": sql_count,
        "sql_queries_per_req": round(sql_count / total, 2) if total else 0.0,
    }


async def _run_scenario(
    name: str,
    concurrency: int,
    total_requests: int,
    fn: Any,
    sql_counter: list[int],
) -> dict[str, Any]:
    latencies: list[float] = []
    errors = 0
    sem = asyncio.Semaphore(concurrency)
    start_sql = sql_counter[0]
    t0 = time.perf_counter()

    async def _one(i: int) -> None:
        nonlocal errors
        async with sem:
            req_t0 = time.perf_counter()
            ok = await fn(i)
            latencies.append((time.perf_counter() - req_t0) * 1000.0)
            if not ok:
                errors += 1

    await asyncio.gather(*[_one(i) for i in range(total_requests)])
    elapsed = time.perf_counter() - t0
    return _summarize(name, latencies, errors, elapsed, sql_counter[0] - start_sql)


async def main() -> None:
    db_url = os.environ["PFA_DATABASE_URL"]
    assert "localhost" in db_url or "127.0.0.1" in db_url, "Refusing non-local database URL"

    # Measure embedder memory footprint
    tracemalloc.start()
    cur_before, _ = tracemalloc.get_traced_memory()
    fake_emb = FakeEmbedder()
    set_embedder(fake_emb)
    _ = fake_emb.embed_query("budget split and emergency fund")
    cur_after, peak_after = tracemalloc.get_traced_memory()
    embedder_mem_kb = round((peak_after - cur_before) / 1024.0, 2)
    tracemalloc.stop()

    # Attach SQL query counter to local engine
    engine = get_async_engine()
    sql_counter = [0]

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count_sql(*_args: Any, **_kwargs: Any) -> None:
        sql_counter[0] += 1

    set_llm_gateway(LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=FakeProvider()))

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localtest") as client:
        # Setup 5 test users
        users: list[tuple[dict[str, str], str]] = []
        for idx in range(5):
            email = f"load_{uuid.uuid4().hex[:8]}_{idx}@example.com"
            reg = await client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "StrongPassword123!", "full_name": f"Load User {idx}"},
            )
            assert reg.status_code == 201, reg.text
            tok = reg.json()["access_token"]
            hdr = {"Authorization": f"Bearer {tok}"}
            c_res = await client.post(
                "/api/v1/auth/consent",
                headers=hdr,
                json={"terms_accepted": True, "privacy_accepted": True, "ai_data_processing_consent": True},
            )
            assert c_res.status_code == 200
            acc = await client.post(
                "/api/v1/plan/accounts",
                headers=hdr,
                json={"name": "HDFC", "account_type": "savings", "institution_name": "HDFC", "account_number_mask": "****9999"},
            )
            assert acc.status_code == 201
            users.append((hdr, acc.json()["id"]))

        # 1. Login scenario
        creds = []
        for idx in range(3):
            em = f"loginload_{uuid.uuid4().hex[:8]}_{idx}@example.com"
            r = await client.post(
                "/api/v1/auth/register",
                json={"email": em, "password": "StrongPassword123!", "full_name": "Login Load"},
            )
            assert r.status_code == 201
            creds.append(em)

        async def _login(i: int) -> bool:
            r = await client.post("/api/v1/auth/login", json={"email": creds[i % len(creds)], "password": "StrongPassword123!"})
            return r.status_code == 200

        results = []
        results.append(await _run_scenario("login", concurrency=5, total_requests=25, fn=_login, sql_counter=sql_counter))

        # 2. Upload CSV scenario
        async def _upload(i: int) -> bool:
            hdr, acc_id = users[i % len(users)]
            csv_body = "Date,Description,Amount,Type\n" + "\n".join(
                f"2026-11-{(j % 28) + 1:02d},Merchant {i}-{j},{100 + j},debit" for j in range(20)
            )
            r = await client.post(
                "/api/v1/plan/upload-statement",
                headers=hdr,
                json={"account_id": acc_id, "format": "csv", "content": csv_body},
            )
            return r.status_code == 200

        results.append(await _run_scenario("upload_csv_20_rows", concurrency=5, total_requests=20, fn=_upload, sql_counter=sql_counter))

        # 3. Home scenario (cash-flow + budget + reminders)
        async def _home(i: int) -> bool:
            hdr, _ = users[i % len(users)]
            r1 = await client.get("/api/v1/plan/cash-flow", headers=hdr)
            r2 = await client.get("/api/v1/plan/budget", headers=hdr)
            r3 = await client.get("/api/v1/recurring/reminders", headers=hdr)
            return r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200

        results.append(await _run_scenario("home_bundle", concurrency=8, total_requests=40, fn=_home, sql_counter=sql_counter))

        # 4. Chat (fake provider)
        async def _chat(i: int) -> bool:
            hdr, _ = users[i % len(users)]
            r = await client.post("/api/v1/assistant/chat", headers=hdr, json={"question": "How is my spending this month?"})
            return r.status_code == 200

        results.append(await _run_scenario("chat_fake_provider", concurrency=5, total_requests=25, fn=_chat, sql_counter=sql_counter))

        # 5. Chat (slow provider 400ms)
        class _SlowProvider(FakeProvider):
            async def generate(self, request: Any) -> Any:
                await asyncio.sleep(0.4)
                return await super().generate(request)

        set_llm_gateway(LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=_SlowProvider()))
        results.append(await _run_scenario("chat_slow_provider_400ms", concurrency=5, total_requests=15, fn=_chat, sql_counter=sql_counter))

        # 6. Mixed users
        set_llm_gateway(LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=FakeProvider()))

        async def _mixed(i: int) -> bool:
            mode = i % 3
            if mode == 0:
                return await _home(i)
            if mode == 1:
                return await _chat(i)
            return await _upload(i)

        results.append(await _run_scenario("mixed_users", concurrency=6, total_requests=30, fn=_mixed, sql_counter=sql_counter))

        # --- Failure Injections ---
        # A. LLM down / 429 -> fallback
        class _RateLimitProvider(FakeProvider):
            async def generate(self, request: Any) -> Any:
                raise RateLimited("429 injected")

        set_llm_gateway(LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=_RateLimitProvider()))
        chat_429 = await client.post("/api/v1/assistant/chat", headers=users[0][0], json={"question": "How is my budget?"})

        # B. Slow DB (150ms injected per dependency yield)
        orig_get_db = get_db

        async def _slow_db_dep() -> Any:
            await asyncio.sleep(0.15)
            async for s in orig_get_db():
                yield s

        app.dependency_overrides[get_db] = _slow_db_dep
        results.append(await _run_scenario("failure_slow_db_150ms", concurrency=5, total_requests=15, fn=_home, sql_counter=sql_counter))

        # C. DB down -> 503 on /ready and API
        async def _down_db_dep() -> Any:
            raise OperationalError("SELECT 1", {}, Exception("injected db down"))

        app.dependency_overrides[get_db] = _down_db_dep
        ready_down = await client.get("/ready")
        home_down = await client.get("/api/v1/plan/cash-flow", headers=users[0][0])
        app.dependency_overrides.clear()

    print("RESULTS:", results)
    print("EMBEDDER_PEAK_KB:", embedder_mem_kb)
    print("FAILURE_LLM_429_STATUS:", chat_429.status_code)
    print("FAILURE_DB_DOWN_READY:", ready_down.status_code, "HOME:", home_down.status_code)


if __name__ == "__main__":
    asyncio.run(main())
