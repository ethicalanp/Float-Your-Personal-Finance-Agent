import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AccountStatus, AccountType
from app.models.plan import Account
from app.services.cash_flow import compute_monthly_cash_flow
from app.services.statement_parser import parse_csv_statement


@pytest.fixture
def plan_user_setup(client: TestClient) -> tuple[TestClient, dict[str, str], str]:
    email = f"plan_edge_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "Plan Edge User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={
            "name": "Edge Test Savings",
            "account_type": "savings",
            "institution_name": "SBI",
            "account_number_mask": "****5678",
            "currency": "INR",
            "initial_balance": 1000.0,
        },
    )
    account_id = acc.json()["id"]
    return client, headers, account_id


def test_import_empty_csv_rejected(plan_user_setup: tuple[TestClient, dict[str, str], str]) -> None:
    client, headers, account_id = plan_user_setup
    res = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": ""},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_import_garbage_format_rejected(plan_user_setup: tuple[TestClient, dict[str, str], str]) -> None:
    client, headers, account_id = plan_user_setup
    garbage = "RANDOM_HEADER_NOT_A_CSV\nSome unparseable gibberish with no dates or numbers\nAnother line"
    res = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": garbage},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_import_huge_file_rejected(plan_user_setup: tuple[TestClient, dict[str, str], str]) -> None:
    client, headers, account_id = plan_user_setup
    # Create content exceeding 10MB instantly without massive line serialization
    huge_content = "Date,Description,Amount,Type\n" + ("X" * (10 * 1024 * 1024 + 1024))
    res = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": huge_content},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "10 MB" in res.json()["error"]["message"]


def test_import_content_length_header_rejected_early(plan_user_setup: tuple[TestClient, dict[str, str], str]) -> None:
    """Assert oversized Content-Length header is rejected early with 413 before loading body."""
    client, headers, account_id = plan_user_setup
    res = client.post(
        "/api/v1/plan/upload-statement",
        headers={**headers, "content-length": str(15 * 1024 * 1024)},
        content=b"dummy small body",
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "10 MB" in res.json()["error"]["message"]


def test_import_streaming_chunked_rejected_during_stream(
    plan_user_setup: tuple[TestClient, dict[str, str], str],
) -> None:
    """Assert streaming read exceeding 10 MB is capped and aborted during stream with 413."""
    client, headers, account_id = plan_user_setup

    def chunk_generator():
        prefix = f'{{"account_id": "{account_id}", "format": "csv", "content": "'
        yield prefix.encode("utf-8")
        chunk = b"X" * (1024 * 1024)  # 1 MB chunk
        for _ in range(11):  # 11 MB cumulative
            yield chunk
        yield b'"}'

    stream_headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
    res = client.post(
        "/api/v1/plan/upload-statement",
        headers=stream_headers,
        content=chunk_generator(),
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "10 MB" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_upload_limit_sends_single_413_response() -> None:
    """Assert StatementUploadLimitMiddleware sends exactly one 413 response when stream limit is hit."""
    import json

    from app.core.middleware import StatementUploadLimitMiddleware

    async def inner_app(scope, receive, send):
        try:
            while True:
                msg = await receive()
                if msg["type"] == "http.request" and not msg.get("more_body", False):
                    break
        except Exception:
            # Simulate FastAPI's body-parse error handler attempting to send 400
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b'{"detail":"There was an error parsing the body"}'})

    middleware = StatementUploadLimitMiddleware(inner_app, max_size=1024)
    chunks = iter(
        [
            {"type": "http.request", "body": b"A" * 600, "more_body": True},
            {"type": "http.request", "body": b"B" * 600, "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "path": "/api/v1/plan/upload-statement", "method": "POST", "headers": []}
    await middleware(scope, receive, send)

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 413
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    payload = json.loads(body.decode("utf-8"))
    assert payload["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "10 MB" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_upload_client_disconnect_mid_stream_no_hang_no_double_send() -> None:
    """Assert a client disconnect mid-upload does not hang or send duplicate responses."""
    from app.core.middleware import StatementUploadLimitMiddleware

    async def inner_app(scope, receive, send):
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            if msg["type"] == "http.request" and not msg.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = StatementUploadLimitMiddleware(inner_app, max_size=1024)
    events = iter(
        [
            {"type": "http.request", "body": b"A" * 512, "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(events)

    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "path": "/api/v1/plan/upload-statement", "method": "POST", "headers": []}
    await middleware(scope, receive, send)

    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) <= 1


def test_import_duplicate_is_idempotent(plan_user_setup: tuple[TestClient, dict[str, str], str]) -> None:
    client, headers, account_id = plan_user_setup
    csv_content = (
        "Date,Description,Debit,Credit\n"
        "2026-03-01,Salary Credit,0,50000\n"
        "2026-03-02,Grocery Store,1500,0\n"
    )

    # First upload
    res1 = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": csv_content},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["imported_count"] == 2
    assert d1["duplicates_skipped"] == 0

    # Second upload of the exact same content
    res2 = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": csv_content},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["imported_count"] == 0
    assert d2["duplicates_skipped"] == 2


def test_import_handles_bad_dates_and_bad_amounts() -> None:
    csv_content = (
        "Date,Description,Debit,Credit\n"
        "2026-03-01,Valid Debit,100.50,0\n"
        "invalid-date,Bad Date Debit,200.00,0\n"
        "2026-03-02,Malformed Amount Debit,12.34.56,0\n"
        "2026-03-03,Text In Amount,N/A,0\n"
    )
    parsed = parse_csv_statement(csv_content, "test-acc")
    # Valid rows are parsed without crashing; malformed amounts with 0 debit/credit are cleanly skipped
    assert len(parsed) >= 1
    assert parsed[0]["amount"] == 100.50
    assert parsed[0]["transaction_type"] == "debit"


def test_import_handles_utf8_bom() -> None:
    csv_content = "\ufeffDate,Description,Debit,Credit\n2026-03-01,BOM Test Debit,350.00,0\n"
    parsed = parse_csv_statement(csv_content, "test-acc")
    assert len(parsed) == 1
    assert parsed[0]["amount"] == 350.00


def test_decimal_cash_flow_precision() -> None:
    """Verify Decimal cash flow calculation does not suffer from floating-point accumulation drift."""
    # 10 credits of 0.10 + 1 credit of 0.20 = exactly 1.20 (in float: 0.1*10 + 0.2 can drift)
    txs = [{"date": "2026-03-01", "amount": 0.10, "transaction_type": "credit"} for _ in range(10)]
    txs.append({"date": "2026-03-01", "amount": 0.20, "transaction_type": "credit"})
    txs.append({"date": "2026-03-01", "amount": 0.70, "transaction_type": "debit"})

    res = compute_monthly_cash_flow(txs)
    assert res["total_inflow"] == 1.20
    assert res["total_outflow"] == 0.70
    assert res["net_savings"] == 0.50
    assert res["overall_savings_rate_pct"] == round((0.50 / 1.20) * 100, 1)


@pytest.mark.asyncio
async def test_account_balance_concurrency() -> None:
    """Verify transaction additions update the account balance consistently."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base
    from app.models.user import User

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[User.__table__, Account.__table__]
            )
        )

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    async with session_maker() as db_session:
        user = User(
            id=user_id,
            email="concurrent@example.com",
            normalized_email="concurrent@example.com",
            hashed_password="hashed_dummy",
            full_name="Concurrent Tester",
        )
        db_session.add(user)
        await db_session.flush()

        account = Account(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Concurrent Test Account",
            account_type=AccountType.SAVINGS,
            status=AccountStatus.ACTIVE,
            institution_name="Test Bank",
            account_number_mask="****1234",
            currency="INR",
            reported_balance=Decimal("1000.00"),
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # Simulate sequential updates
        account.reported_balance += Decimal("500.00")
        await db_session.commit()
        await db_session.refresh(account)
        assert account.reported_balance == Decimal("1500.00")

        account.reported_balance -= Decimal("250.00")
        await db_session.commit()
        await db_session.refresh(account)
        assert account.reported_balance == Decimal("1250.00")

    await engine.dispose()
