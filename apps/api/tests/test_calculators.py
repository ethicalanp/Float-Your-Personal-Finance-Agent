import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.services.calculators_service import (
    calculate_insurance_gap,
    calculate_sip_projection,
    compare_tax_regimes,
)


def _register_and_consent(client: TestClient, prefix: str) -> dict[str, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "Calc User"},
    )
    assert res.status_code == 201
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    c_res = client.post(
        "/api/v1/auth/consent",
        headers=headers,
        json={"terms_accepted": True, "privacy_accepted": True, "ai_data_processing_consent": True},
    )
    assert c_res.status_code == 200
    return headers


def test_sip_projection_known_math_and_inflation_toggle() -> None:
    # Zero return -> exact principal sum
    zero_res = calculate_sip_projection(
        monthly_sip_paise=1_000_000,  # ₹10,000
        lumpsum_paise=5_000_000,  # ₹50,000
        years=10,
        expected_return_pct=Decimal("0"),
        adjust_for_inflation=False,
    )
    assert zero_res.total_invested_paise == 125_000_000
    assert zero_res.projected_nominal_paise == 125_000_000
    assert zero_res.projected_real_paise == 125_000_000

    # Standard SIP: ₹10,000/mo for 10 years at 12% p.a. monthly compounding
    # Formula: 10000 * ((1.01^120 - 1) / 0.01) = 23,00,386.89 -> 230038689 paise
    std = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        lumpsum_paise=0,
        years=10,
        expected_return_pct=Decimal("12"),
        adjust_for_inflation=True,
        inflation_pct=Decimal("6"),
    )
    assert std.total_invested_paise == 120_000_000
    assert std.projected_nominal_paise == 230_038_689
    assert std.projected_real_paise < std.projected_nominal_paise
    assert [s.annual_return_pct for s in std.illustrative_scenarios] == [
        Decimal("8"),
        Decimal("10"),
        Decimal("12"),
    ]
    assert "not a guarantee" in std.disclaimer.lower()


def test_insurance_gap_heuristic_and_no_dependants() -> None:
    gap_res = calculate_insurance_gap(
        annual_income_paise=120_000_000,  # ₹12L
        dependants=2,
        existing_life_cover_paise=500_000_000,  # ₹50L
        existing_health_cover_paise=500_000_00,  # ₹5L
        liabilities_paise=200_000_000,  # ₹20L
    )
    # Life = 10 * 12L + 20L = 1.4 Cr; gap = 90L
    assert gap_res.recommended_life_cover_paise == 1_400_000_000
    assert gap_res.life_cover_gap_paise == 900_000_000
    assert gap_res.life_status == "gap"
    # Health = 5L + 2 * 2.5L = 10L; gap = 5L
    assert gap_res.recommended_health_cover_paise == 100_000_000
    assert gap_res.health_cover_gap_paise == 50_000_000
    assert gap_res.health_status == "gap"
    assert "no insurance product" in gap_res.disclaimer.lower()

    no_dep = calculate_insurance_gap(
        annual_income_paise=120_000_000,
        dependants=0,
        existing_life_cover_paise=0,
        existing_health_cover_paise=60_000_000,
    )
    assert no_dep.recommended_life_cover_paise == 0
    assert no_dep.life_status == "no_dependants_note"
    assert no_dep.health_status == "covered"


def test_tax_regime_comparison_known_examples() -> None:
    # Salaried ₹12,75,000 -> New regime taxable ₹12,00,000 -> 87A rebate makes tax = ₹0
    r1275 = compare_tax_regimes(gross_income_paise=127_500_000, is_salaried=True)
    assert r1275.verified is True
    assert r1275.needs_verified_parameters is False
    assert r1275.source_url.startswith("https://www.incometax.gov.in")
    assert r1275.new_regime.taxable_income_paise == 120_000_000
    assert r1275.new_regime.total_tax_paise == 0
    assert r1275.lower_tax_regime == "new"

    # Salaried ₹5,50,000 -> Old regime taxable ₹5,00,000 -> 87A rebate makes Old tax = ₹0
    r550 = compare_tax_regimes(gross_income_paise=55_000_000, is_salaried=True)
    assert r550.old_regime.taxable_income_paise == 50_000_000
    assert r550.old_regime.total_tax_paise == 0
    assert r550.new_regime.total_tax_paise == 0
    assert r550.lower_tax_regime == "equal"

    # ₹25,00,000 salaried with 80C ₹1.5L + 80D ₹50k
    # New taxable = ₹24,25,000 -> slab tax ₹3,07,500 + 4% cess = ₹3,19,800
    r25 = compare_tax_regimes(
        gross_income_paise=250_000_000,
        is_salaried=True,
        deduction_80c_paise=15_000_000,
        deduction_80d_paise=5_000_000,
    )
    assert r25.new_regime.slab_tax_paise == 30_750_000
    assert r25.new_regime.cess_paise == 1_230_000
    assert r25.new_regime.total_tax_paise == 31_980_000


def test_calculator_endpoints_and_assistant_tools(client: TestClient) -> None:
    headers = _register_and_consent(client, "calcs")

    sip_res = client.post(
        "/api/v1/plan/calculators/sip",
        headers=headers,
        json={"monthly_sip_paise": 1_000_000, "years": 10, "expected_return_pct": 12},
    )
    assert sip_res.status_code == 200
    assert sip_res.json()["projected_nominal_paise"] == 230_038_689

    ins_res = client.post(
        "/api/v1/plan/calculators/insurance-gap",
        headers=headers,
        json={
            "annual_income_paise": 120_000_000,
            "dependants": 1,
            "existing_life_cover_paise": 0,
            "existing_health_cover_paise": 0,
        },
    )
    assert ins_res.status_code == 200
    assert ins_res.json()["recommended_life_cover_paise"] == 1_200_000_000

    tax_res = client.post(
        "/api/v1/plan/calculators/tax-compare",
        headers=headers,
        json={"gross_income_paise": 127_500_000, "is_salaried": True},
    )
    assert tax_res.status_code == 200
    assert tax_res.json()["new_regime"]["total_tax_paise"] == 0

    for q in (
        "Calculate my SIP projection for 10 years",
        "Check my insurance gap for life cover",
        "Compare old regime vs new regime income tax",
    ):
        chat = client.post("/api/v1/assistant/chat", headers=headers, json={"question": q})
        assert chat.status_code == 200
