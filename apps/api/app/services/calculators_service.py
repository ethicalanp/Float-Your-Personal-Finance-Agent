import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

TAX_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tax_regimes.json"


# ---------------------------------------------------------------------------
# 1. SIP & Projection Calculator (Educational Only)
# ---------------------------------------------------------------------------


class YearlySipRowOut(BaseModel):
    year: int
    invested_paise: int
    nominal_value_paise: int
    real_value_paise: int
    returns_paise: int
    monthly_contribution_paise: int


class SipScenarioOut(BaseModel):
    label: str
    annual_return_pct: Decimal
    nominal_corpus_paise: int
    real_corpus_paise: int
    total_invested_paise: int
    nominal_gain_paise: int


class SipProjectionResponse(BaseModel):
    mode: Literal["forward", "reverse"] = "forward"
    monthly_sip_paise: int
    target_amount_paise: int | None = None
    required_starting_sip_paise: int | None = None
    lumpsum_paise: int
    years: int
    expected_return_pct: Decimal
    step_up_type: Literal["none", "percent", "amount"] = "none"
    step_up_interval_months: int = 12
    step_up_percent: Decimal = Decimal("0")
    step_up_amount_paise: int = 0
    adjust_for_inflation: bool
    inflation_pct: Decimal
    total_invested_paise: int
    estimated_returns_paise: int
    projected_nominal_paise: int
    projected_real_paise: int
    plain_sip_invested_paise: int
    plain_sip_nominal_paise: int
    extra_from_stepup_paise: int
    yearly_schedule: list[YearlySipRowOut]
    illustrative_scenarios: list[SipScenarioOut]
    assumptions: list[str]
    disclaimer: str
    final_monthly_contribution_paise: int = 0
    final_monthly_contribution_year: int = 0
    unrealistic_contribution_warning: bool = False
    unrealistic_warning_reason: str | None = None


def _simulate_sip_decimal(
    starting_monthly_paise: Decimal,
    lumpsum_paise: Decimal,
    years: int,
    annual_return_pct: Decimal,
    step_up_type: Literal["none", "percent", "amount"] = "none",
    step_up_interval_months: int = 12,
    step_up_percent: Decimal = Decimal("0"),
    step_up_amount_paise: Decimal = Decimal("0"),
    adjust_for_inflation: bool = True,
    inflation_pct: Decimal = Decimal("6"),
) -> tuple[Decimal, Decimal, list[YearlySipRowOut]]:
    """Simulate monthly compounding (annual/12), start-of-month contributions, and block step-ups in Decimal."""
    monthly_rate = (
        (annual_return_pct / Decimal("100")) / Decimal("12") if annual_return_pct > Decimal("0") else Decimal("0")
    )
    balance = lumpsum_paise
    total_invested = lumpsum_paise
    schedule: list[YearlySipRowOut] = []
    interval = max(1, step_up_interval_months)
    step_factor = Decimal("1") + (step_up_percent / Decimal("100"))

    for month in range(1, years * 12 + 1):
        block_idx = (month - 1) // interval
        if step_up_type == "percent" and step_up_percent > Decimal("0"):
            contrib = starting_monthly_paise * (step_factor**block_idx)
        elif step_up_type == "amount" and step_up_amount_paise > Decimal("0"):
            contrib = starting_monthly_paise + (Decimal(block_idx) * step_up_amount_paise)
        else:
            contrib = starting_monthly_paise

        total_invested += contrib
        balance = (balance + contrib) * (Decimal("1") + monthly_rate)

        if month % 12 == 0:
            yr = month // 12
            inv_p = int(total_invested.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            nom_p = int(balance.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            real_p = _adjust_for_inflation_paise(nom_p, yr, inflation_pct) if adjust_for_inflation else nom_p
            contrib_p = int(contrib.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            schedule.append(
                YearlySipRowOut(
                    year=yr,
                    invested_paise=inv_p,
                    nominal_value_paise=nom_p,
                    real_value_paise=real_p,
                    returns_paise=nom_p - inv_p,
                    monthly_contribution_paise=contrib_p,
                )
            )

    return total_invested, balance, schedule


def _adjust_for_inflation_paise(nominal_paise: int, years: int, inflation_pct: Decimal) -> int:
    if inflation_pct <= Decimal("0") or years <= 0:
        return nominal_paise
    factor = (Decimal("1") + inflation_pct / Decimal("100")) ** years
    return int((Decimal(nominal_paise) / factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_sip_projection(
    monthly_sip_paise: int,
    lumpsum_paise: int = 0,
    years: int = 10,
    expected_return_pct: Decimal = Decimal("10"),
    adjust_for_inflation: bool = True,
    inflation_pct: Decimal = Decimal("6"),
    mode: Literal["forward", "reverse"] = "forward",
    target_amount_paise: int | None = None,
    step_up_type: Literal["none", "percent", "amount"] = "none",
    step_up_interval_months: int = 12,
    step_up_percent: Decimal = Decimal("0"),
    step_up_amount_paise: int = 0,
    monthly_income_paise: int | None = None,
    max_income_share_pct: Decimal = Decimal("50"),
) -> SipProjectionResponse:
    """Calculate deterministic forward or reverse SIP + step-up + lumpsum projection in Decimal."""
    effective_step_type = step_up_type
    if step_up_type == "percent" and step_up_percent <= Decimal("0"):
        effective_step_type = "none"
    elif step_up_type == "amount" and step_up_amount_paise <= 0:
        effective_step_type = "none"

    required_sip: int | None = None
    starting_sip_dec = Decimal(monthly_sip_paise)

    if mode == "reverse":
        target_dec = Decimal(target_amount_paise or 0)
        # Maturity is linear in starting_sip: M(S) = M_lumpsum + M_fixed_steps + S * M(1)
        _, fv_lumpsum, _ = _simulate_sip_decimal(
            Decimal("0"), Decimal(lumpsum_paise), years, expected_return_pct, "none", step_up_interval_months
        )
        fv_fixed_steps = Decimal("0")
        if effective_step_type == "amount":
            _, fv_fixed_steps, _ = _simulate_sip_decimal(
                Decimal("0"),
                Decimal("0"),
                years,
                expected_return_pct,
                "amount",
                step_up_interval_months,
                Decimal("0"),
                Decimal(step_up_amount_paise),
            )
        unit_step_type: Literal["none", "percent", "amount"] = (
            "percent" if effective_step_type == "percent" else "none"
        )
        _, fv_unit, _ = _simulate_sip_decimal(
            Decimal("1"),
            Decimal("0"),
            years,
            expected_return_pct,
            unit_step_type,
            step_up_interval_months,
            step_up_percent,
            Decimal("0"),
        )
        needed = max(Decimal("0"), target_dec - fv_lumpsum - fv_fixed_steps)
        starting_sip_dec = needed / fv_unit if fv_unit > Decimal("0") else Decimal("0")
        required_sip = int(starting_sip_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        monthly_sip_paise = required_sip

    inv_dec, nom_dec, yearly_schedule = _simulate_sip_decimal(
        starting_sip_dec,
        Decimal(lumpsum_paise),
        years,
        expected_return_pct,
        effective_step_type,
        step_up_interval_months,
        step_up_percent,
        Decimal(step_up_amount_paise),
        adjust_for_inflation,
        inflation_pct,
    )
    total_invested = int(inv_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    nom_main = int(nom_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    real_main = _adjust_for_inflation_paise(nom_main, years, inflation_pct) if adjust_for_inflation else nom_main

    plain_inv_dec, plain_nom_dec, _ = _simulate_sip_decimal(
        starting_sip_dec,
        Decimal(lumpsum_paise),
        years,
        expected_return_pct,
        "none",
        step_up_interval_months,
        Decimal("0"),
        Decimal("0"),
        adjust_for_inflation,
        inflation_pct,
    )
    plain_inv = int(plain_inv_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    plain_nom = int(plain_nom_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    band_rates = [
        ("Conservative (8% p.a.)", Decimal("8")),
        ("Moderate (10% p.a.)", Decimal("10")),
        ("Growth (12% p.a.)", Decimal("12")),
    ]
    scenarios: list[SipScenarioOut] = []
    for label, rate in band_rates:
        sc_inv_d, sc_nom_d, _ = _simulate_sip_decimal(
            starting_sip_dec,
            Decimal(lumpsum_paise),
            years,
            rate,
            effective_step_type,
            step_up_interval_months,
            step_up_percent,
            Decimal(step_up_amount_paise),
            adjust_for_inflation,
            inflation_pct,
        )
        sc_inv = int(sc_inv_d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        sc_nom = int(sc_nom_d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        real = _adjust_for_inflation_paise(sc_nom, years, inflation_pct) if adjust_for_inflation else sc_nom
        scenarios.append(
            SipScenarioOut(
                label=label,
                annual_return_pct=rate,
                nominal_corpus_paise=sc_nom,
                real_corpus_paise=real,
                total_invested_paise=sc_inv,
                nominal_gain_paise=sc_nom - sc_inv,
            )
        )

    final_monthly_paise = (
        yearly_schedule[-1].monthly_contribution_paise
        if yearly_schedule
        else int(starting_sip_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    )
    final_monthly_year = years
    unrealistic_warning = False
    unrealistic_reason: str | None = None
    if mode == "forward" and effective_step_type != "none" and starting_sip_dec > Decimal("0"):
        exceeds_3x = Decimal(final_monthly_paise) > (starting_sip_dec * Decimal("3"))
        exceeds_income = (
            monthly_income_paise is not None
            and monthly_income_paise > 0
            and Decimal(final_monthly_paise) > (Decimal(monthly_income_paise) * max_income_share_pct / Decimal("100"))
        )
        if exceeds_3x and exceeds_income:
            unrealistic_warning = True
            unrealistic_reason = "exceeds_3x_and_income_share"
        elif exceeds_3x:
            unrealistic_warning = True
            unrealistic_reason = "exceeds_3x_starting"
        elif exceeds_income:
            unrealistic_warning = True
            unrealistic_reason = "exceeds_income_share"

    assumptions = [
        "Monthly compounding at annual_return / 12 with contributions at the start of each month.",
        f"Step-up applied at the start of each {step_up_interval_months}-month block ({effective_step_type}).",
        f"Inflation adjustment {'enabled' if adjust_for_inflation else 'disabled'} at {inflation_pct}% p.a.",
        "Illustrative mathematical projection only; excludes taxes, exit loads, and expense ratios.",
    ]
    return SipProjectionResponse(
        mode=mode,
        monthly_sip_paise=monthly_sip_paise,
        target_amount_paise=target_amount_paise,
        required_starting_sip_paise=required_sip,
        lumpsum_paise=lumpsum_paise,
        years=years,
        expected_return_pct=expected_return_pct,
        step_up_type=effective_step_type,
        step_up_interval_months=step_up_interval_months,
        step_up_percent=step_up_percent,
        step_up_amount_paise=step_up_amount_paise,
        adjust_for_inflation=adjust_for_inflation,
        inflation_pct=inflation_pct,
        total_invested_paise=total_invested,
        estimated_returns_paise=nom_main - total_invested,
        projected_nominal_paise=nom_main,
        projected_real_paise=real_main,
        plain_sip_invested_paise=plain_inv,
        plain_sip_nominal_paise=plain_nom,
        extra_from_stepup_paise=nom_main - plain_nom,
        yearly_schedule=yearly_schedule,
        illustrative_scenarios=scenarios,
        assumptions=assumptions,
        disclaimer=(
            "Illustrative mathematical projection only — not a guarantee of returns, "
            "not advice; taxes and fees ignored."
        ),
        final_monthly_contribution_paise=final_monthly_paise,
        final_monthly_contribution_year=final_monthly_year,
        unrealistic_contribution_warning=unrealistic_warning,
        unrealistic_warning_reason=unrealistic_reason,
    )


# ---------------------------------------------------------------------------
# 2. Insurance Gap Check (Transparent Heuristic, No Product Advice)
# ---------------------------------------------------------------------------


class InsuranceGapResponse(BaseModel):
    annual_income_paise: int
    dependants: int
    existing_life_cover_paise: int
    recommended_life_cover_paise: int
    life_cover_gap_paise: int
    life_status: Literal["covered", "gap", "no_dependants_note"]
    existing_health_cover_paise: int
    recommended_health_cover_paise: int
    health_cover_gap_paise: int
    health_status: Literal["covered", "gap"]
    assumptions: list[str]
    disclaimer: str


def calculate_insurance_gap(
    annual_income_paise: int,
    dependants: int,
    existing_life_cover_paise: int,
    existing_health_cover_paise: int,
    liabilities_paise: int = 0,
) -> InsuranceGapResponse:
    """Compute a transparent educational insurance gap heuristic without product recommendations."""
    income_multiplier = 10 if dependants > 0 else 0
    rec_life = (annual_income_paise * income_multiplier) + (liabilities_paise if dependants > 0 else 0)
    life_gap = max(0, rec_life - existing_life_cover_paise)
    life_status: Literal["covered", "gap", "no_dependants_note"] = (
        "no_dependants_note" if dependants == 0 else ("covered" if life_gap == 0 else "gap")
    )

    # Health cover heuristic: ₹5L base + ₹2.5L per dependant (in paise)
    base_health = 50_000_000
    per_dep_health = 25_000_000
    rec_health = base_health + (dependants * per_dep_health)
    health_gap = max(0, rec_health - existing_health_cover_paise)
    health_status: Literal["covered", "gap"] = "covered" if health_gap == 0 else "gap"

    assumptions = [
        "Life cover heuristic: 10x annual income + outstanding liabilities when dependants > 0 (0x if no dependants).",
        "Health cover heuristic: ₹5,00,000 base for self + ₹2,50,000 per dependant.",
        (
            "Does not account for employer group cover exclusions, city-tier hospital costs, "
            "or existing medical conditions."
        ),
    ]
    return InsuranceGapResponse(
        annual_income_paise=annual_income_paise,
        dependants=dependants,
        existing_life_cover_paise=existing_life_cover_paise,
        recommended_life_cover_paise=rec_life,
        life_cover_gap_paise=life_gap,
        life_status=life_status,
        existing_health_cover_paise=existing_health_cover_paise,
        recommended_health_cover_paise=rec_health,
        health_cover_gap_paise=health_gap,
        health_status=health_status,
        assumptions=assumptions,
        disclaimer="Educational heuristic only — no insurance product or insurer recommendations.",
    )


# ---------------------------------------------------------------------------
# 3. Tax Regime Comparison (Versioned Parameters File)
# ---------------------------------------------------------------------------


class RegimeBreakdownOut(BaseModel):
    regime: str
    gross_income_paise: int
    total_deductions_paise: int
    taxable_income_paise: int
    slab_tax_paise: int
    rebate_87a_paise: int
    cess_paise: int
    total_tax_paise: int


class TaxComparisonResponse(BaseModel):
    version: str
    financial_year: str
    as_of: str
    source_url: str
    verified: bool
    needs_verified_parameters: bool
    old_regime: RegimeBreakdownOut
    new_regime: RegimeBreakdownOut
    lower_tax_regime: Literal["old", "new", "equal"]
    estimated_difference_paise: int
    educational_notice: str


@lru_cache(maxsize=1)
def load_tax_parameters() -> dict[str, Any]:
    with TAX_DATA_PATH.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _compute_slab_tax_paise(taxable_paise: int, slabs: list[dict[str, Any]]) -> int:
    if taxable_paise <= 0:
        return 0
    tax = Decimal("0")
    prev_limit = 0
    for slab in slabs:
        up_to = slab["up_to_paise"]
        rate = Decimal(str(slab["rate_pct"])) / Decimal("100")
        if up_to is None:
            band = max(0, taxable_paise - prev_limit)
            tax += Decimal(band) * rate
            break
        if taxable_paise > prev_limit:
            band = min(taxable_paise, int(up_to)) - prev_limit
            tax += Decimal(band) * rate
        prev_limit = int(up_to)
        if taxable_paise <= prev_limit:
            break
    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _evaluate_regime(
    gross_income_paise: int,
    deductions_paise: int,
    regime_cfg: dict[str, Any],
    cess_pct: int,
) -> RegimeBreakdownOut:
    taxable = max(0, gross_income_paise - deductions_paise)
    slab_tax = _compute_slab_tax_paise(taxable, regime_cfg["slabs"])
    rebate = 0
    if taxable <= int(regime_cfg["rebate_87a_max_taxable_paise"]):
        rebate = min(slab_tax, int(regime_cfg["rebate_87a_max_amount_paise"]))
    tax_after_rebate = max(0, slab_tax - rebate)
    cess = int(
        (Decimal(tax_after_rebate) * Decimal(cess_pct) / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return RegimeBreakdownOut(
        regime=str(regime_cfg["label"]),
        gross_income_paise=gross_income_paise,
        total_deductions_paise=deductions_paise,
        taxable_income_paise=taxable,
        slab_tax_paise=slab_tax,
        rebate_87a_paise=rebate,
        cess_paise=cess,
        total_tax_paise=tax_after_rebate + cess,
    )


def compare_tax_regimes(
    gross_income_paise: int,
    is_salaried: bool = True,
    deduction_80c_paise: int = 0,
    deduction_80d_paise: int = 0,
    other_deductions_paise: int = 0,
) -> TaxComparisonResponse:
    """Compare Old vs New tax regimes deterministically from the versioned parameters file."""
    cfg = load_tax_parameters()
    cess_pct = int(cfg["cess_pct"])

    new_cfg = cfg["new_regime"]
    new_std = int(new_cfg["standard_deduction_paise"]) if is_salaried else 0
    new_out = _evaluate_regime(gross_income_paise, min(gross_income_paise, new_std), new_cfg, cess_pct)

    old_cfg = cfg["old_regime"]
    old_std = int(old_cfg["standard_deduction_paise"]) if is_salaried else 0
    capped_80c = min(max(0, deduction_80c_paise), int(old_cfg["max_80c_paise"]))
    capped_80d = min(max(0, deduction_80d_paise), int(old_cfg["max_80d_paise"]))
    old_ded = min(gross_income_paise, old_std + capped_80c + capped_80d + max(0, other_deductions_paise))
    old_out = _evaluate_regime(gross_income_paise, old_ded, old_cfg, cess_pct)

    diff = abs(old_out.total_tax_paise - new_out.total_tax_paise)
    if new_out.total_tax_paise < old_out.total_tax_paise:
        lower: Literal["old", "new", "equal"] = "new"
    elif old_out.total_tax_paise < new_out.total_tax_paise:
        lower = "old"
    else:
        lower = "equal"

    return TaxComparisonResponse(
        version=str(cfg["version"]),
        financial_year=str(cfg["financial_year"]),
        as_of=str(cfg["as_of"]),
        source_url=str(cfg["source_url"]),
        verified=bool(cfg["verified"]),
        needs_verified_parameters=bool(cfg["needs_verified_parameters"]),
        old_regime=old_out,
        new_regime=new_out,
        lower_tax_regime=lower,
        estimated_difference_paise=diff,
        educational_notice=str(cfg["educational_notice"]),
    )
