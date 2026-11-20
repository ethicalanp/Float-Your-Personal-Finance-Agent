
from fastapi.testclient import TestClient

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
        database_url="sqlite+aiosqlite:///:memory:",
        _env_file=None,
    )
    prod_client = TestClient(create_app(production))

    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404
    assert prod_client.get("/api/v1/health").status_code == 200