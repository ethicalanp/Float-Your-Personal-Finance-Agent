import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db


def test_ready_and_api_return_503_when_database_is_down(client: TestClient) -> None:
    email = f"db503_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "DB Down User"},
    )
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    async def _down_db() -> AsyncGenerator[Any, None]:
        raise OperationalError("SELECT 1", {}, Exception("injected db down"))
        yield  # pragma: no cover

    client.app.dependency_overrides[get_db] = _down_db  # type: ignore[attr-defined]
    try:
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["error"]["code"] == "DATABASE_UNAVAILABLE"

        cf = client.get("/api/v1/plan/cash-flow", headers=headers)
        assert cf.status_code == 503
        assert cf.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
