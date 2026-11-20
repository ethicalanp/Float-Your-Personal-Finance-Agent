import uuid
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AccountType, TransactionType
from app.models.plan import Account, Transaction
from app.models.recurring import RecurringCommitment

FEATURE_VERSION = "v1.1.0"
FEATURE_COLUMNS = (
    "monthly_inflow_avg",
    "income_volatility_cov",
    "income_sources_count",
    "debt_to_income_ratio",
    "expense_to_income_ratio",
    "fixed_expense_ratio",
    "savings_rate_pct",
    "buffer_runway_months",
    "min_balance_ratio",
    "negative_balance_events",
)

SUPPORTED_BASE_CURRENCY = "INR"

_LIQUID_ACCOUNT_TYPES = {
    AccountType.SAVINGS,
    AccountType.CHECKING,
    AccountType.WALLET,
}
_FIXED_EXPENSE_TERMS = ("rent", "housing", "utility", "utilities")
_DEBT_TERMS = ("emi", "loan", "debt")
_EXCLUDED_INCOME_TERMS = (
    "refund",
    "reversal",
    "cashback",
    "self transfer",
    "internal transfer",
    "account transfer",
    "own a/c",
    "own account",
    "credit card bill payment",
)
_EXCLUDED_EXPENSE_TERMS = (
    "refund",
    "reversal",
    "self transfer",
    "internal transfer",
    "account transfer",
    "own a/c",
    "own account",
    "credit card bill payment",
    "credit card payment",
    "cc payment",
)
_EARNED_INCOME_CATEGORIES = {
    "income & salary",
    "salary",
    "wages",
    "payroll",
    "professional fee",
    "freelance",
    "interest",
    "business income",
}


def _is_earned_income(category: str, description: str, merchant: str | None) -> bool:
    if category.strip().casefold() not in _EARNED_INCOME_CATEGORIES:
        return False

    evidence = " ".join((description, merchant or "")).casefold()
    return not any(term in evidence for term in _EXCLUDED_INCOME_TERMS)


def _is_expense(category: str, description: str) -> bool:
    if category.strip().casefold() == "transfers":
        return False
    evidence = f"{category} {description}".casefold()
    return not any(term in evidence for term in _EXCLUDED_EXPENSE_TERMS)


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def _monthly_amount(amount: float, frequency: str) -> float:
    if frequency == "quarterly":
        return amount / 3.0
    if frequency == "yearly":
        return amount / 12.0
    return amount


async def extract_borrow_features(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Extract versioned aggregates; identifiers and transaction text never leave this function."""
    account_result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.currency == SUPPORTED_BASE_CURRENCY,
        )
    )
    accounts = account_result.scalars().all()
    liquid_balance = sum(
        float(account.reported_balance)
        for account in accounts
        if account.status.value == "active" and account.account_type in _LIQUID_ACCOUNT_TYPES
    )

    transaction_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.currency == SUPPORTED_BASE_CURRENCY)
        .order_by(Transaction.transaction_date.asc())
    )
    transactions = transaction_result.scalars().all()

    if not transactions:
        return {
            "feature_version": FEATURE_VERSION,
            "transaction_count": 0,
            "observed_month_count": 0,
            "monthly_inflow_avg": 0.0,
            "income_volatility_cov": None,
            "income_sources_count": 0,
            "debt_to_income_ratio": None,
            "expense_to_income_ratio": None,
            "fixed_expense_ratio": None,
            "savings_rate_pct": None,
            "buffer_runway_months": None,
            "min_balance_ratio": None,
            "negative_balance_events": None,
            "balance_history_available": False,
        }

    # Use at most six months, bounded by the dates actually present in the statement history.
    first_month = _month_index(transactions[0].transaction_date.date())
    last_month = _month_index(transactions[-1].transaction_date.date())
    window_start = max(first_month, last_month - 5)
    observed_months = list(range(window_start, last_month + 1))
    credits_by_month: dict[int, float] = defaultdict(float)
    debits_by_month: dict[int, float] = defaultdict(float)
    income_sources: set[str] = set()
    transaction_count = 0

    for transaction in transactions:
        month = _month_index(transaction.transaction_date.date())
        if month < window_start:
            continue

        transaction_count += 1
        amount = float(transaction.amount)
        if transaction.transaction_type == TransactionType.CREDIT:
            if _is_earned_income(
                transaction.category,
                transaction.description_cleaned or transaction.description,
                transaction.normalized_merchant or transaction.merchant,
            ):
                credits_by_month[month] += amount
                source = (transaction.normalized_merchant or transaction.merchant or "").strip().casefold()
                if source:
                    income_sources.add(source)
        else:
            if _is_expense(
                transaction.category,
                transaction.description_cleaned or transaction.description,
            ):
                debits_by_month[month] += amount

    monthly_credits = [credits_by_month[month] for month in observed_months]
    monthly_debits = [debits_by_month[month] for month in observed_months]
    average_inflow = sum(monthly_credits) / len(observed_months)
    average_expense = sum(monthly_debits) / len(observed_months)
    total_inflow = sum(monthly_credits)
    total_expense = sum(monthly_debits)

    if len(monthly_credits) >= 2 and average_inflow > 0:
        variance = sum((amount - average_inflow) ** 2 for amount in monthly_credits) / len(monthly_credits)
        income_volatility_cov = (variance**0.5) / average_inflow
    else:
        income_volatility_cov = None

    commitments_result = await db.execute(
        select(RecurringCommitment).where(
            RecurringCommitment.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
        )
    )
    commitments = commitments_result.scalars().all()
    monthly_fixed_expenses = 0.0
    monthly_debt_payments = 0.0
    for commitment in commitments:
        amount = _monthly_amount(float(commitment.expected_amount), commitment.frequency)
        category = commitment.category.casefold()
        if any(term in category for term in _FIXED_EXPENSE_TERMS):
            monthly_fixed_expenses += amount
        if any(term in category for term in _DEBT_TERMS):
            monthly_debt_payments += amount

    if average_inflow > 0:
        debt_to_income_ratio = monthly_debt_payments / average_inflow
        expense_to_income_ratio = average_expense / average_inflow
        fixed_expense_ratio = monthly_fixed_expenses / average_inflow
        savings_rate_pct = 100.0 * (total_inflow - total_expense) / total_inflow if total_inflow else None
    else:
        debt_to_income_ratio = None
        expense_to_income_ratio = None
        fixed_expense_ratio = None
        savings_rate_pct = None

    buffer_runway_months = liquid_balance / average_expense if average_expense > 0 else None

    return {
        "feature_version": FEATURE_VERSION,
        "transaction_count": transaction_count,
        "observed_month_count": len(observed_months),
        "monthly_inflow_avg": round(average_inflow, 2),
        "income_volatility_cov": round(income_volatility_cov, 4) if income_volatility_cov is not None else None,
        "income_sources_count": len(income_sources),
        "debt_to_income_ratio": round(debt_to_income_ratio, 4) if debt_to_income_ratio is not None else None,
        "expense_to_income_ratio": round(expense_to_income_ratio, 4) if expense_to_income_ratio is not None else None,
        "fixed_expense_ratio": round(fixed_expense_ratio, 4) if fixed_expense_ratio is not None else None,
        "savings_rate_pct": round(savings_rate_pct, 2) if savings_rate_pct is not None else None,
        "buffer_runway_months": round(buffer_runway_months, 2) if buffer_runway_months is not None else None,
        # Current schema stores only the latest reported balance, not a balance timeline.
        "min_balance_ratio": None,
        "negative_balance_events": None,
        "balance_history_available": False,
    }
