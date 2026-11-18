from fastapi.testclient import TestClient


def test_request_id_generated_and_returned_in_headers(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    assert len(res.headers["X-Request-ID"]) > 10


def test_incoming_request_id_preserved(client: TestClient) -> None:
    custom_id = "custom-trace-uuid-12345"
    res = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers["X-Request-ID"] == custom_id


def test_unified_error_format_404(client: TestClient) -> None:
    res = client.get("/api/v1/non-existent-endpoint")
    assert res.status_code == 404
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
    assert "request_id" in body["error"]


def test_unified_error_format_422(client: TestClient) -> None:
    # Post invalid payload to auth/register (missing required fields)
    res = client.post("/api/v1/auth/register", json={"email": "not-an-email"})
    assert res.status_code == 422
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in body["error"]
    assert len(body["error"]["details"]) > 0
