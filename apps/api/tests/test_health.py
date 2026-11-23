import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.main import create_app


def test_health_check(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_unknown_path_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_api_docs_are_available_outside_production(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_api_docs_are_hidden_in_production() -> None:
    production = Settings(
        app_env="production",
        jwt_secret_key="test-production-secret-key-with-at-least-32-characters",
        database_url="postgresql+psycopg://test:test@localhost/test",
        _env_file=None,
    )
    prod_client = TestClient(create_app(production))

    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404
    assert prod_client.get("/api/v1/health").status_code == 200


def test_sqlite_startup_skips_postgres_only_knowledge_chunks(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}"
    settings = Settings(app_env="development", database_url=database_url, _env_file=None)
    application = create_app(settings)
    engine = create_async_engine(database_url)
    monkeypatch.setattr("app.db.session.get_async_engine", lambda: engine)

    async def start_and_read_tables() -> list[str]:
        async with application.router.lifespan_context(application):
            async with engine.connect() as connection:
                return await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

    try:
        table_names = asyncio.run(start_and_read_tables())
    finally:
        asyncio.run(engine.dispose())

    assert "users" in table_names
    assert "knowledge_documents" in table_names
    assert "knowledge_chunks" not in table_names
