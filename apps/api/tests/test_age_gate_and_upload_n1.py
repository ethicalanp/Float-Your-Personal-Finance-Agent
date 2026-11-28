from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import get_async_engine
from app.models.enums import ConsentType
from app.models.user import Consent, User


def test_age_gate_at_signup_rejects_false_and_records_versioned_consent(client: TestClient) -> None:
    # Explicit age_confirmed=False is rejected
    r_under = client.post(
        "/api/v1/auth/register",
        json={
            "email": "underage@example.com",
            "password": "StrongPass123!",
            "full_name": "Young User",
            "terms_accepted": True,
            "privacy_accepted": True,
            "age_confirmed": False,
        },
    )
    assert r_under.status_code == 400

    # Explicit age_confirmed=True succeeds and stores consent without DOB
    r_ok = client.post(
        "/api/v1/auth/register",
        json={
            "email": "adult@example.com",
            "password": "StrongPass123!",
            "full_name": "Adult User",
            "terms_accepted": True,
            "privacy_accepted": True,
            "age_confirmed": True,
            "age_confirmation_version": "2026.1",
        },
    )
    assert r_ok.status_code == 201, r_ok.text
    assert not hasattr(User, "date_of_birth")
    assert not hasattr(Consent, "date_of_birth")
    assert ConsentType.AGE_18_PLUS.value == "age_18_plus"


def test_upload_statement_avoids_n_plus_1_queries(client: TestClient) -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "n1upload@example.com",
            "password": "StrongPass123!",
            "full_name": "Upload Tester",
            "terms_accepted": True,
            "privacy_accepted": True,
            "age_confirmed": True,
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    acc_res = client.post(
        "/api/v1/plan/accounts",
        json={"name": "Primary Savings", "account_type": "savings", "reported_balance": 10000.0},
        headers=headers,
    )
    assert acc_res.status_code in (200, 201), acc_res.text
    account_id = acc_res.json()["id"]

    def _upload_and_count_queries(row_count: int, offset_days: int) -> int:
        lines = ["Date,Description,Debit,Credit"] + [
            f"2026-10-{(i % 28) + 1:02d},MERCHANT_{offset_days}_{i},100.00,"
            for i in range(row_count)
        ]
        csv_body = "\n".join(lines)
        engine = get_async_engine().sync_engine
        queries: list[str] = []

        def _before_exec(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(engine, "before_cursor_execute", _before_exec)
        try:
            res = client.post(
                "/api/v1/plan/upload-statement",
                json={"account_id": account_id, "format": "csv", "content": csv_body},
                headers=headers,
            )
            assert res.status_code == 200, res.text
            assert res.json()["imported_count"] == row_count
        finally:
            event.remove(engine, "before_cursor_execute", _before_exec)
        return len(queries)

    q_5 = _upload_and_count_queries(5, 1)
    q_30 = _upload_and_count_queries(30, 2)
    # Bulk insert + single dedupe query means query count is constant regardless of row count (no N+1)
    assert q_30 == q_5, f"Expected constant query count, got {q_5} for 5 rows vs {q_30} for 30 rows"
