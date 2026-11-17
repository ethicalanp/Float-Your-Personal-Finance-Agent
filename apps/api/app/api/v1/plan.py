import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import BadRequestException, NotFoundException
from app.core.security import CurrentUser, get_current_user
from app.services.cash_flow import compute_financial_insights, compute_monthly_cash_flow
from app.services.statement_parser import parse_csv_statement, parse_sms_statement

router = APIRouter(prefix="/plan", tags=["Plan — Personal Finance Management"])

# In-memory storage for testability & dev environments
_ACCOUNTS_DB: dict[str, dict[str, Any]] = {}
_TRANSACTIONS_DB: dict[str, list[dict[str, Any]]] = {}  # user_id -> list of transactions
_SEEN_FINGERPRINTS: set[str] = set()


class CreateAccountRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Primary HDFC Savings"})
    account_type: str = Field("savings", json_schema_extra={"example": "savings"})  # savings, checking, credit_card
    institution_name: str = Field("HDFC Bank", json_schema_extra={"example": "HDFC Bank"})
    account_number_mask: str = Field("****1234", json_schema_extra={"example": "****1234"})
    currency: str = Field("INR", json_schema_extra={"example": "INR"})
    initial_balance: float = Field(0.0, json_schema_extra={"example": 50000.0})


class AccountResponse(BaseModel):
    id: str
    user_id: str
    name: str
    account_type: str
    institution_name: str
    account_number_mask: str
    currency: str
    current_balance: float
    created_at: str


class UploadStatementRequest(BaseModel):
    account_id: str
    format: str = Field("csv", json_schema_extra={"example": "csv"})  # csv or sms
    content: str = Field(..., description="Raw text of the CSV or bank SMS alert")


class StatementUploadSummary(BaseModel):
    account_id: str
    total_parsed: int
    imported_count: int
    duplicates_skipped: int
    sample_imported: list[dict[str, Any]]


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(
    req: CreateAccountRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AccountResponse:
    """Create a new financial account (savings, checking, credit card)."""
    acc_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    account: dict[str, Any] = {
        "id": acc_id,
        "user_id": current_user.user_id,
        "name": req.name,
        "account_type": req.account_type,
        "institution_name": req.institution_name,
        "account_number_mask": req.account_number_mask,
        "currency": req.currency,
        "current_balance": req.initial_balance,
        "created_at": now,
    }
    _ACCOUNTS_DB[acc_id] = account
    return AccountResponse(**account)


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[AccountResponse]:
    """Retrieve all accounts belonging to the authenticated user."""
    user_accs = [acc for acc in _ACCOUNTS_DB.values() if acc["user_id"] == current_user.user_id]
    return [AccountResponse(**acc) for acc in user_accs]


@router.post("/upload-statement", response_model=StatementUploadSummary)
async def upload_statement(
    req: UploadStatementRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StatementUploadSummary:
    """Upload a bank statement (CSV or SMS text) with automatic deduplication, sanitization, and categorization."""
    account = _ACCOUNTS_DB.get(req.account_id)
    if not account or account["user_id"] != current_user.user_id:
        raise NotFoundException("Specified account does not exist or does not belong to you.")

    if req.format.lower() == "sms":
        parsed_single = parse_sms_statement(req.content, req.account_id)
        parsed_txs = [parsed_single] if parsed_single else []
    else:
        parsed_txs = parse_csv_statement(req.content, req.account_id)

    if not parsed_txs:
        raise BadRequestException("Could not extract any valid transactions from the provided content.")

    user_tx_list = _TRANSACTIONS_DB.setdefault(current_user.user_id, [])
    imported: list[dict[str, Any]] = []
    skipped_count = 0

    for tx in parsed_txs:
        fp = tx["fingerprint"]
        if fp in _SEEN_FINGERPRINTS:
            skipped_count += 1
            continue

        _SEEN_FINGERPRINTS.add(fp)
        tx_record = dict(tx)
        tx_record["id"] = str(uuid.uuid4())
        tx_record["user_id"] = current_user.user_id

        # Update account balance accordingly
        amt = tx_record["amount"]
        if tx_record["transaction_type"] == "credit":
            account["current_balance"] += amt
        else:
            account["current_balance"] -= amt

        # Format date for JSON serialization
        if isinstance(tx_record["date"], datetime):
            tx_record["date"] = tx_record["date"].isoformat()

        user_tx_list.append(tx_record)
        imported.append(tx_record)

    return StatementUploadSummary(
        account_id=req.account_id,
        total_parsed=len(parsed_txs),
        imported_count=len(imported),
        duplicates_skipped=skipped_count,
        sample_imported=imported[:5],
    )


@router.get("/transactions")
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List transactions with optional filtering by account and category."""
    txs = _TRANSACTIONS_DB.get(current_user.user_id, [])
    filtered = txs
    if account_id:
        filtered = [t for t in filtered if t.get("account_id") == account_id]
    if category:
        filtered = [t for t in filtered if t.get("category", "").lower() == category.lower()]
    return filtered


@router.get("/cash-flow")
async def get_cash_flow(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Calculate monthly cash flow (inflow, outflow, net savings, savings rate)."""
    txs = _TRANSACTIONS_DB.get(current_user.user_id, [])
    return compute_monthly_cash_flow(txs)


@router.get("/insights")
async def get_insights(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve personal finance insights: income volatility, balance runway, top spending categories."""
    txs = _TRANSACTIONS_DB.get(current_user.user_id, [])
    user_accs = [acc for acc in _ACCOUNTS_DB.values() if acc["user_id"] == current_user.user_id]
    total_balance = sum(acc["current_balance"] for acc in user_accs)
    return compute_financial_insights(txs, current_balance=total_balance)
