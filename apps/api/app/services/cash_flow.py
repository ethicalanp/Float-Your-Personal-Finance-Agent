import math
from collections import defaultdict
from datetime import datetime
from typing import Any


def compute_monthly_cash_flow(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate month-by-month inflow, outflow, net savings, and savings rate."""
    months_data: dict[str, dict[str, float]] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0})

    for tx in transactions:
        tx_date = tx.get("date")
        if isinstance(tx_date, str):
            month_key = tx_date[:7]
        elif isinstance(tx_date, datetime):
            month_key = tx_date.strftime("%Y-%m")
        else:
            month_key = "unknown"

        amount = float(tx.get("amount", 0.0))
        t_type = tx.get("transaction_type", "debit").lower()

        if t_type == "credit":
            months_data[month_key]["inflow"] += amount
        else:
            months_data[month_key]["outflow"] += amount

    sorted_months = sorted(months_data.keys())
    breakdown = []
    total_inflow = 0.0
    total_outflow = 0.0

    for m in sorted_months:
        inflow = round(months_data[m]["inflow"], 2)
        outflow = round(months_data[m]["outflow"], 2)
        net_savings = round(inflow - outflow, 2)
        savings_rate = round((net_savings / inflow * 100), 1) if inflow > 0 else 0.0

        total_inflow += inflow
        total_outflow += outflow

        breakdown.append({
            "month": m,
            "inflow": inflow,
            "outflow": outflow,
            "net_savings": net_savings,
            "savings_rate_pct": savings_rate,
        })

    net_total = round(total_inflow - total_outflow, 2)
    overall_savings_rate = round((net_total / total_inflow * 100), 1) if total_inflow > 0 else 0.0

    return {
        "total_inflow": round(total_inflow, 2),
        "total_outflow": round(total_outflow, 2),
        "net_savings": net_total,
        "overall_savings_rate_pct": overall_savings_rate,
        "monthly_breakdown": breakdown,
    }


def compute_financial_insights(
    transactions: list[dict[str, Any]],
    current_balance: float = 0.0,
) -> dict[str, Any]:
    """Calculate key financial health indicators: income volatility, balance buffer, and top spending."""
    cash_flow = compute_monthly_cash_flow(transactions)
    monthly_data = cash_flow["monthly_breakdown"]

    # 1. Income Volatility Index
    monthly_inflows = [m["inflow"] for m in monthly_data if m["inflow"] > 0]
    if len(monthly_inflows) >= 2:
        mean_income = sum(monthly_inflows) / len(monthly_inflows)
        variance = sum((x - mean_income) ** 2 for x in monthly_inflows) / len(monthly_inflows)
        std_dev = math.sqrt(variance)
        cov = std_dev / mean_income if mean_income > 0 else 0.0

        if cov < 0.15:
            volatility_tier = "LOW"
            volatility_explanation = "Your monthly income is highly predictable and stable."
        elif cov < 0.35:
            volatility_tier = "MODERATE"
            volatility_explanation = "Your income shows moderate month-to-month variation."
        else:
            volatility_tier = "HIGH"
            volatility_explanation = "Significant fluctuation in monthly earnings detected."
    elif len(monthly_inflows) == 1:
        mean_income = monthly_inflows[0]
        cov = 0.0
        volatility_tier = "LOW"
        volatility_explanation = "Single month income baseline established."
    else:
        mean_income = 0.0
        cov = 0.0
        volatility_tier = "UNKNOWN"
        volatility_explanation = "Insufficient income history to evaluate volatility."

    # 2. Balance Buffer / Runway
    monthly_outflows = [m["outflow"] for m in monthly_data if m["outflow"] > 0]
    avg_monthly_expense = (sum(monthly_outflows) / len(monthly_outflows)) if monthly_outflows else 1.0
    daily_expense = avg_monthly_expense / 30.0

    if daily_expense > 0 and current_balance > 0:
        buffer_days = round(current_balance / daily_expense, 1)
        buffer_months = round(current_balance / avg_monthly_expense, 2)
    else:
        buffer_days = 0.0
        buffer_months = 0.0

    if buffer_months >= 3.0:
        buffer_status = "HEALTHY"
        buffer_advice = f"Strong financial cushion of {buffer_months} months ({buffer_days} days)."
    elif buffer_months >= 1.0:
        buffer_status = "MODERATE"
        buffer_advice = f"Moderate buffer of {buffer_months} months. Recommended safety target is 3 to 6 months."
    else:
        buffer_status = "AT_RISK"
        buffer_advice = "Low buffer reserve (< 1 month). Prioritize building an emergency liquidity cushion."

    # 3. Top Spending Categories
    category_spending: dict[str, float] = defaultdict(float)
    total_expense = 0.0

    for tx in transactions:
        if tx.get("transaction_type", "debit").lower() == "debit":
            amt = float(tx.get("amount", 0.0))
            cat = tx.get("category", "Other")
            category_spending[cat] += amt
            total_expense += amt

    sorted_categories = sorted(category_spending.items(), key=lambda x: x[1], reverse=True)
    top_categories = []
    for cat, amt in sorted_categories[:5]:
        pct = round((amt / total_expense * 100), 1) if total_expense > 0 else 0.0
        top_categories.append({
            "category": cat,
            "amount": round(amt, 2),
            "percentage": pct,
        })

    return {
        "income_volatility": {
            "tier": volatility_tier,
            "coefficient_of_variation": round(cov, 3),
            "average_monthly_income": round(mean_income, 2),
            "summary": volatility_explanation,
        },
        "balance_buffer": {
            "current_balance": round(current_balance, 2),
            "average_monthly_expense": round(avg_monthly_expense, 2),
            "runway_days": buffer_days,
            "runway_months": buffer_months,
            "status": buffer_status,
            "advice": buffer_advice,
        },
        "top_spending_categories": top_categories,
    }
