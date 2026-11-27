import uuid

from fastapi.testclient import TestClient


def _register_and_consent(client: TestClient, prefix: str) -> tuple[dict[str, str], str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "Chat User"},
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    c_res = client.post(
        "/api/v1/auth/consent",
        headers=headers,
        json={"terms_accepted": True, "privacy_accepted": True, "ai_data_processing_consent": True},
    )
    assert c_res.status_code == 200
    return headers, res.json()["user_id"]


def test_conversation_crud_cross_user_404_and_feedback(client: TestClient) -> None:
    h1, _ = _register_and_consent(client, "chat1")
    h2, _ = _register_and_consent(client, "chat2")

    # Knowledge Q&A persists Conversation + user/assistant Messages for user 1
    k_res = client.post(
        "/api/v1/assistant/knowledge",
        headers=h1,
        json={"question": "What is the 1930 cybercrime helpline?", "language_hint": "en"},
    )
    assert k_res.status_code == 200

    convs1 = client.get("/api/v1/assistant/conversations", headers=h1).json()
    assert len(convs1) == 1
    cid = convs1[0]["id"]

    # User 2 sees 0 conversations
    assert client.get("/api/v1/assistant/conversations", headers=h2).json() == []

    # Cross-user GET messages / PATCH / DELETE -> 404
    assert client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h2).status_code == 404
    patch_res = client.patch(f"/api/v1/assistant/conversations/{cid}", headers=h2, json={"title": "Hacked"})
    assert patch_res.status_code == 404
    assert client.delete(f"/api/v1/assistant/conversations/{cid}", headers=h2).status_code == 404

    # Owner can read messages, rename, submit feedback, and delete
    msgs = client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h1)
    assert msgs.status_code == 200 and len(msgs.json()) >= 2

    ren = client.patch(f"/api/v1/assistant/conversations/{cid}", headers=h1, json={"title": "Fraud Help"})
    assert ren.status_code == 200 and ren.json()["title"] == "Fraud Help"

    fb = client.post(
        "/api/v1/assistant/feedback",
        headers=h1,
        json={"rating": "down", "trace_id": k_res.json().get("trace_id"), "reason": "Too brief"},
    )
    assert fb.status_code == 201 and fb.json()["status"] == "recorded"

    assert client.delete(f"/api/v1/assistant/conversations/{cid}", headers=h1).status_code == 204
    assert client.get(f"/api/v1/assistant/conversations/{cid}/messages", headers=h1).status_code == 404


def test_chat_stream_flag_and_sse_response(client: TestClient, monkeypatch) -> None:
    h1, _ = _register_and_consent(client, "stream1")

    # Disabled by default -> 501
    off_res = client.post(
        "/api/v1/assistant/chat/stream",
        headers=h1,
        json={"question": "What is 50/30/20 rule?"},
    )
    assert off_res.status_code == 501

    # Enabled via PFA_ENABLE_CHAT_STREAMING / get_settings() -> text/event-stream
    from app.api.v1 import assistant as assistant_mod

    class _StreamSettings:
        enable_chat_streaming = True

    monkeypatch.setattr(assistant_mod, "get_settings", lambda: _StreamSettings())
    on_res = client.post(
        "/api/v1/assistant/chat/stream",
        headers=h1,
        json={"question": "What is 50/30/20 rule?"},
    )
    assert on_res.status_code == 200
    assert "text/event-stream" in on_res.headers["content-type"]
    assert "event: delta" in on_res.text and "event: done" in on_res.text
