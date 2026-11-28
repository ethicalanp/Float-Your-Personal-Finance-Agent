import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.ai.tools.base import ToolContext
from app.ai.tools.financial_tools import NetWorthInput, handle_get_net_worth
from app.models.subscriptions_networth import NetWorthItem


def _register_and_consent(client: TestClient, prefix: str) -> tuple[dict[str, str], str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "Sub NW User"},
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


def test_no_data_defaults(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "snwnodata")

    leaks = client.get("/api/v1/plan/subscriptions/leaks", headers=headers)
    assert leaks.status_code == 200
    assert leaks.json() == {
        "total_leaks": 0,
        "estimated_yearly_savings_paise": 0,
        "potential_yearly_savings_paise": 0,
        "leaks": [],
    }

    nw = client.get("/api/v1/plan/net-worth", headers=headers)
    assert nw.status_code == 200
    assert nw.json() == {
        "total_assets_paise": 0,
        "total_liabilities_paise": 0,
        "net_worth_paise": 0,
        "is_negative": False,
        "stale_count": 0,
        "items": [],
        "snapshots": [],
    }


def test_subscription_leak_rules_dedup_and_decisions(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "subleaks")

    # 1. Duplicate commitments + small_recurring on Spotify (triggers both rules, deduplicated to 1 item)
    for idx in range(2):
        r = client.post(
            "/api/v1/recurring/commitments",
            headers=headers,
            json={
                "name": f"Spotify Plan {idx + 1}",
                "category": "Subscriptions",
                "expected_amount": 119,
                "frequency": "monthly",
                "due_rule_day": 5,
                "merchant": "Spotify",
                "merchant_keywords": ["spotify"],
                "start_date": "2026-10-01",
            },
        )
        assert r.status_code == 201

    # 2. Annual renewal (₹7,200/yr = ₹600/mo -> above small_recurring threshold)
    r_ann = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Amazon Prime",
            "category": "Subscriptions",
            "expected_amount": 7200,
            "frequency": "yearly",
            "due_rule_day": 10,
            "merchant": "Amazon Prime",
            "merchant_keywords": ["prime"],
            "start_date": "2026-01-10",
        },
    )
    assert r_ann.status_code == 201

    # 3. Upload statement for price_increase (Netflix 499 -> 649) and trial_to_paid (Canva 99 -> 499)
    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "HDFC", "account_type": "savings", "institution_name": "HDFC", "account_number_mask": "****2222"},
    ).json()
    up = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": acc["id"],
            "format": "csv",
            "content": (
                "Date,Description,Amount,Type\n"
                "2026-10-01,Netflix Plan,499,debit\n"
                "2026-11-01,Netflix Plan,649,debit\n"
                "2026-10-15,Canva Pro,99,debit\n"
                "2026-11-02,Canva Pro,499,debit\n"
            ),
        },
    )
    assert up.status_code == 200

    res = client.get("/api/v1/plan/subscriptions/leaks", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total_leaks"] == 4
    by_key = {item["leak_key"]: item for item in body["leaks"]}

    # Spotify deduplicated across small_recurring and duplicate
    assert "spotify" in by_key
    assert set(by_key["spotify"]["rules_triggered"]) == {"small_recurring", "duplicate"}
    assert by_key["amazon prime"]["rules_triggered"] == ["annual_renewal"]
    assert "price_increase" in by_key["netflix plan"]["rules_triggered"]
    assert "trial_to_paid" in by_key["canva pro"]["rules_triggered"]

    assert body["estimated_yearly_savings_paise"] == 0
    assert body["potential_yearly_savings_paise"] > 0

    # Mark Netflix as cancel -> estimated yearly savings = 649 * 100 * 12 = 778800 paise
    c_res = client.put(
        "/api/v1/plan/subscriptions/leaks/netflix%20plan",
        headers=headers,
        json={"decision": "cancel"},
    )
    assert c_res.status_code == 200
    assert c_res.json()["estimated_yearly_savings_paise"] == 778_800

    # Mark Amazon Prime as keep -> potential savings drops
    k_res = client.put(
        "/api/v1/plan/subscriptions/leaks/amazon%20prime",
        headers=headers,
        json={"decision": "keep"},
    )
    assert k_res.status_code == 200
    assert k_res.json()["potential_yearly_savings_paise"] < body["potential_yearly_savings_paise"]


def test_net_worth_crud_negative_stale_concurrency_cross_user_and_dpdp(client: TestClient) -> None:
    h1, _ = _register_and_consent(client, "nw1")
    h2, _ = _register_and_consent(client, "nw2")

    stale_date = (datetime.now(UTC) - timedelta(days=45)).isoformat()

    # Create asset (stale) and larger liability -> negative net worth
    a_res = client.post(
        "/api/v1/plan/net-worth/items",
        headers=h1,
        json={
            "name": "Emergency Savings",
            "item_type": "asset",
            "category": "cash",
            "amount_paise": 250_000_00,  # ₹2.5L
            "valued_at": stale_date,
        },
    )
    assert a_res.status_code == 201
    l_res = client.post(
        "/api/v1/plan/net-worth/items",
        headers=h1,
        json={
            "name": "Education Loan",
            "item_type": "liability",
            "category": "loan",
            "amount_paise": 500_000_00,  # ₹5L
        },
    )
    assert l_res.status_code == 201
    ov = l_res.json()
    assert ov["total_assets_paise"] == 25_000_000
    assert ov["total_liabilities_paise"] == 50_000_000
    assert ov["net_worth_paise"] == -25_000_000
    assert ov["is_negative"] is True
    assert ov["stale_count"] == 1

    asset_item = [i for i in ov["items"] if i["item_type"] == "asset"][0]
    assert asset_item["is_stale"] is True
    assert asset_item["days_since_update"] >= 45

    # Dated snapshot
    snap_res = client.post(
        "/api/v1/plan/net-worth/snapshots",
        headers=h1,
        json={"snapshot_date": "2026-11-01"},
    )
    assert snap_res.status_code == 201
    assert len(snap_res.json()["snapshots"]) == 1
    assert snap_res.json()["snapshots"][0]["net_worth_paise"] == -25_000_000

    # Cross-user 404
    assert (
        client.put(
            f"/api/v1/plan/net-worth/items/{asset_item['id']}",
            headers=h2,
            json={"amount_paise": 100},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/plan/net-worth/items/{asset_item['id']}", headers=h2).status_code == 404

    # Update asset + 409 on stale version
    u_ok = client.put(
        f"/api/v1/plan/net-worth/items/{asset_item['id']}",
        headers=h1,
        json={"amount_paise": 60_000_000, "expected_version": 1},
    )
    assert u_ok.status_code == 200
    assert u_ok.json()["is_negative"] is False
    assert u_ok.json()["stale_count"] == 0

    u_conflict = client.put(
        f"/api/v1/plan/net-worth/items/{asset_item['id']}",
        headers=h1,
        json={"amount_paise": 70_000_000, "expected_version": 1},
    )
    assert u_conflict.status_code == 409

    # Assistant tool endpoints work with real data
    chat_leaks = client.post(
        "/api/v1/assistant/chat",
        headers=h1,
        json={"question": "Check my subscription leaks"},
    )
    assert chat_leaks.status_code == 200
    chat_nw = client.post(
        "/api/v1/assistant/chat",
        headers=h1,
        json={"question": "What is my net worth?"},
    )
    assert chat_nw.status_code == 200

    # DPDP Export includes sensitive net worth items & snapshots
    exp = client.post("/api/v1/me/export", headers=h1)
    assert exp.status_code == 200
    exp_json = exp.json()
    assert len(exp_json["net_worth_items"]) == 2
    assert len(exp_json["net_worth_snapshots"]) == 1

    # Delete item
    d_item = client.delete(f"/api/v1/plan/net-worth/items/{asset_item['id']}", headers=h1)
    assert d_item.status_code == 200
    assert len(d_item.json()["items"]) == 1

    # DPDP Delete purges remaining items & snapshots cleanly
    del_me = client.delete("/api/v1/me", headers=h1)
    assert del_me.status_code == 200


async def test_net_worth_tool_masks_pii_in_item_names() -> None:
    class _FakeScalarResult:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def scalars(self) -> "_FakeScalarResult":
            return self

        def all(self) -> list[object]:
            return self._rows

    class _FakeSession:
        def __init__(self, items: list[NetWorthItem]) -> None:
            self._items = items
            self._calls = 0

        def execute(self, _stmt: object) -> _FakeScalarResult:
            self._calls += 1
            if self._calls == 1:
                return _FakeScalarResult(self._items)
            return _FakeScalarResult([])

    uid = uuid.uuid4()
    sensitive_item = NetWorthItem(
        id=uuid.uuid4(),
        user_id=uid,
        name="HDFC 9876543210 alice@okaxis",
        item_type="asset",
        category="bank",
        amount_paise=100_000,
        version=1,
        valued_at=datetime.now(UTC),
    )
    ctx = ToolContext(user_id=uid, request_id="test-req", session=_FakeSession([sensitive_item]))  # type: ignore[arg-type]
    res = await handle_get_net_worth(ctx, NetWorthInput())
    name_out = res.data["masked_items"][0]["name_masked"]
    assert "9876543210" not in name_out
    assert "alice@okaxis" not in name_out
