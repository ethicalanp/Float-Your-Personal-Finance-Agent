import uuid
from decimal import Decimal

import pytest
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

    # Start-of-month SIP (annuity-due): ₹10,000/mo for 10 years at 12% p.a. monthly compounding
    # Formula: 10000 * ((1.01^120 - 1) / 0.01) * 1.01 = 23,23,390.76 -> 232339076 paise
    std = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        lumpsum_paise=0,
        years=10,
        expected_return_pct=Decimal("12"),
        adjust_for_inflation=True,
        inflation_pct=Decimal("6"),
    )
    assert std.total_invested_paise == 120_000_000
    assert std.projected_nominal_paise == 232_339_076
    assert std.estimated_returns_paise == 112_339_076
    assert std.projected_real_paise < std.projected_nominal_paise
    assert len(std.yearly_schedule) == 10
    assert [s.annual_return_pct for s in std.illustrative_scenarios] == [
        Decimal("8"),
        Decimal("10"),
        Decimal("12"),
    ]
    assert "not a guarantee" in std.disclaimer.lower()


def test_sip_golden_stepup_example_matches_independent_loop() -> None:
    """Golden example: ₹10,000/mo, 10% p.a., 10 years, 5% step-up every 3 months.

    Hand-computed / block formula:
      - 40 blocks of 3 months (total 120 months), start-of-month contributions, r = 0.10 / 12
      - Total invested = 3 * 10,000 * ((1.05^40 - 1) / 0.05) = ₹3,623,993.23 (362,399,323 paise)
      - Nominal maturity = ₹5,331,228.36 (533,122,836 paise)
      - Plain SIP (no step-up) = ₹2,065,520.20 (206,552,020 paise)
      - Extra from step-up = ₹3,265,708.16 (326,570,816 paise)
    """
    res = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        lumpsum_paise=0,
        years=10,
        expected_return_pct=Decimal("10"),
        adjust_for_inflation=False,
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("5"),
    )
    assert res.total_invested_paise == 362_399_323
    assert res.projected_nominal_paise == 533_122_836
    assert res.plain_sip_nominal_paise == 206_552_020
    assert res.extra_from_stepup_paise == 326_570_816

    # Independent loop check using Python float/Decimal
    r = Decimal("10") / Decimal("100") / Decimal("12")
    bal = Decimal("0")
    inv = Decimal("0")
    for m in range(1, 121):
        c = Decimal("1000000") * (Decimal("1.05") ** ((m - 1) // 3))
        inv += c
        bal = (bal + c) * (Decimal("1") + r)
    assert abs(res.total_invested_paise - int(round(float(inv)))) <= 1
    assert abs(res.projected_nominal_paise - int(round(float(bal)))) <= 1


def test_sip_property_invariants_and_reverse_mode() -> None:
    # 1. 0% return equals total invested (even with step-up)
    z = calculate_sip_projection(
        monthly_sip_paise=500_000,
        lumpsum_paise=1_000_000,
        years=5,
        expected_return_pct=Decimal("0"),
        step_up_type="percent",
        step_up_interval_months=6,
        step_up_percent=Decimal("10"),
        adjust_for_inflation=False,
    )
    assert z.projected_nominal_paise == z.total_invested_paise
    assert z.estimated_returns_paise == 0

    # 2. 0% step-up equals plain SIP
    plain = calculate_sip_projection(monthly_sip_paise=1_000_000, years=8, expected_return_pct=Decimal("10"))
    zero_step = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=8,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("0"),
    )
    assert zero_step.projected_nominal_paise == plain.projected_nominal_paise
    assert zero_step.extra_from_stepup_paise == 0

    # 3. Monotonic in amount, years, and return
    base = calculate_sip_projection(monthly_sip_paise=1_000_000, years=10, expected_return_pct=Decimal("10"))
    more_amt = calculate_sip_projection(monthly_sip_paise=1_500_000, years=10, expected_return_pct=Decimal("10"))
    more_yrs = calculate_sip_projection(monthly_sip_paise=1_000_000, years=12, expected_return_pct=Decimal("10"))
    more_ret = calculate_sip_projection(monthly_sip_paise=1_000_000, years=10, expected_return_pct=Decimal("12"))
    assert more_amt.projected_nominal_paise > base.projected_nominal_paise
    assert more_yrs.projected_nominal_paise > base.projected_nominal_paise
    assert more_ret.projected_nominal_paise > base.projected_nominal_paise

    # 4. reverse(forward(x)) ~= x (within 100 paise = ₹1 rounding)
    fwd = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=10,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("5"),
        adjust_for_inflation=False,
    )
    rev = calculate_sip_projection(
        monthly_sip_paise=0,
        years=10,
        expected_return_pct=Decimal("10"),
        mode="reverse",
        target_amount_paise=fwd.projected_nominal_paise,
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("5"),
        adjust_for_inflation=False,
    )
    assert rev.required_starting_sip_paise is not None
    assert abs(rev.required_starting_sip_paise - 1_000_000) <= 100

    # 5. Fixed-amount step-up & step interval == tenure (1 block -> no step applied)
    one_yr = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=1,
        expected_return_pct=Decimal("10"),
        step_up_type="amount",
        step_up_interval_months=12,
        step_up_amount_paise=200_000,
    )
    assert one_yr.extra_from_stepup_paise == 0


def test_sip_unrealistic_contribution_warning() -> None:
    # 5% step-up every 3 months over 10 years -> final monthly > 3x starting -> triggers warning
    triggered = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=10,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("5"),
    )
    assert triggered.unrealistic_contribution_warning is True
    assert triggered.unrealistic_warning_reason == "exceeds_3x_starting"
    assert triggered.final_monthly_contribution_year == 10
    assert triggered.final_monthly_contribution_paise == 6_704_751

    # 1-year plan with 5% every 3 months -> final is ~1.16x starting -> does NOT trigger
    short_plan = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=1,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("5"),
    )
    assert short_plan.unrealistic_contribution_warning is False

    # 0% step-up over 10 years -> does NOT trigger
    zero_step = calculate_sip_projection(
        monthly_sip_paise=1_000_000,
        years=10,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=3,
        step_up_percent=Decimal("0"),
    )
    assert zero_step.unrealistic_contribution_warning is False

    # Configurable budget income share threshold triggers even under 3x
    income_warn = calculate_sip_projection(
        monthly_sip_paise=1_000_000,  # ₹10,000
        years=3,
        expected_return_pct=Decimal("10"),
        step_up_type="percent",
        step_up_interval_months=12,
        step_up_percent=Decimal("10"),  # final ₹12,100 (< 3x)
        monthly_income_paise=2_000_000,  # ₹20,000 -> 50% = ₹10,000
        max_income_share_pct=Decimal("50"),
    )
    assert income_warn.unrealistic_contribution_warning is True
    assert income_warn.unrealistic_warning_reason == "exceeds_income_share"


@pytest.mark.asyncio
async def test_sip_tool_emits_unrealistic_warning_fact() -> None:
    from unittest.mock import MagicMock

    from app.ai.tools.base import ToolContext
    from app.ai.tools.financial_tools import SipProjectionToolInput, handle_calculate_sip_projection

    ctx = ToolContext(user_id=1, request_id="test-sip-warn", session=MagicMock())
    res = await handle_calculate_sip_projection(
        ctx,
        SipProjectionToolInput(
            monthly_sip_inr=Decimal("10000"),
            years=10,
            expected_return_pct=Decimal("10"),
            step_up_type="percent",
            step_up_interval_months=3,
            step_up_percent=Decimal("5"),
        ),
    )
    assert res.ok is True
    assert res.data["unrealistic_contribution_warning"] is True
    assert res.data["final_monthly_contribution_year"] == 10
    assert any(f.id == "sip_unrealistic_contribution_warning" for f in res.facts)


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
    assert sip_res.json()["projected_nominal_paise"] == 232_339_076

    # Invalid negative SIP and missing reverse target
    bad_neg = client.post(
        "/api/v1/plan/calculators/sip",
        headers=headers,
        json={"monthly_sip_paise": -100, "years": 10},
    )
    assert bad_neg.status_code == 422

    bad_rev = client.post(
        "/api/v1/plan/calculators/sip",
        headers=headers,
        json={"mode": "reverse", "years": 10},
    )
    assert bad_rev.status_code == 400

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
