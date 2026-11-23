from typing import Any

from app.models.enums import ReadinessBand

LEGAL_DISCLAIMER = (
    "This indicative financial-readiness estimate is for educational purposes only. It is not a credit score, "
    "credit decision, loan offer, or guarantee of approval or interest rate. A regulated lender makes its own "
    "independent assessment."
)


def generate_borrow_recommendations(
    readiness_band: ReadinessBand,
    negative_factors: list[dict[str, Any]],
    features: dict[str, Any],
) -> list[dict[str, str]]:
    """Turn adverse SHAP contributors into cautious, actionable financial guidance."""
    adverse_features = {factor["feature"] for factor in negative_factors}
    recommendations: list[dict[str, str]] = []

    runway = features.get("buffer_runway_months")
    if "buffer_runway_months" in adverse_features and runway is not None and runway < 1.5:
        recommendations.append(
            {
                "category": "Emergency savings",
                "title": "Build more liquidity",
                "action": (
                    f"Your recorded cash-flow history suggests about {runway:.1f} months of expense coverage. "
                    "Consider gradually building an emergency reserve before taking on additional commitments."
                ),
            }
        )

    expense_ratio = features.get("expense_to_income_ratio")
    if "expense_to_income_ratio" in adverse_features and expense_ratio is not None and expense_ratio > 0.80:
        recommendations.append(
            {
                "category": "Cash-flow flexibility",
                "title": "Review discretionary expenses",
                "action": (
                    "Recorded expenses are high relative to inflows. Review flexible spending and choose a "
                    "manageable reduction target; even a small sustained change can improve monthly cash flow."
                ),
            }
        )

    volatility = features.get("income_volatility_cov")
    if "income_volatility_cov" in adverse_features and volatility is not None and volatility > 0.50:
        recommendations.append(
            {
                "category": "Income consistency",
                "title": "Track income over a longer period",
                "action": (
                    "Recent monthly inflows vary substantially. Continue tracking verified deposits; several "
                    "consecutive months of records can help you understand whether the variation is temporary."
                ),
            }
        )

    debt_ratio = features.get("debt_to_income_ratio")
    if "debt_to_income_ratio" in adverse_features and debt_ratio is not None and debt_ratio > 0.35:
        recommendations.append(
            {
                "category": "Debt commitments",
                "title": "Review existing repayments",
                "action": (
                    "Review existing loan and EMI commitments against income. Avoid taking on new debt until "
                    "you understand how repayments fit your budget."
                ),
            }
        )

    negative_events = features.get("negative_balance_events")
    if "negative_balance_events" in adverse_features and negative_events is not None and negative_events > 0:
        recommendations.append(
            {
                "category": "Account buffer",
                "title": "Reduce negative-balance periods",
                "action": (
                    "Recorded balance history includes negative-balance events. Consider alerts or a small "
                    "cash buffer to help avoid overdrafts and declined payments."
                ),
            }
        )

    if not recommendations and readiness_band == ReadinessBand.STRONG:
        recommendations.append(
            {
                "category": "Maintain good habits",
                "title": "Keep tracking your cash flow",
                "action": (
                    "Continue reviewing your budget and maintaining a reserve. This estimate is not a lender "
                    "decision or a guarantee of loan terms."
                ),
            }
        )

    return recommendations
