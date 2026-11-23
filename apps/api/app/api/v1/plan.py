import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import BadRequestException, NotFoundException
from app.models.enums import (
    AccountStatus,
    AccountType,
    ConsentType,
    ImportStatus,
    TransactionSource,
    TransactionType,
)
from app.models.plan import Account, Transaction, TransactionImport
from app.models.user import User
from app.services.cash_flow import compute_financial_insights, compute_monthly_cash_flow
from app.services.recurring_service import match_transaction_to_occurrence
from app.services.statement_parser import parse_csv_statement, parse_sms_statement

router = APIRouter(prefix="/plan", tags=["Plan — Personal Finance Management"])


class CreateAccountRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Primary HDFC Savings"})
    account_type: str = Field("savings", json_schema_extra={"example": "savings"})  # savings, checking, credit_card
    institution_name: str = Field("HDFC Bank", json_schema_extra={"example": "HDFC Bank"})
    account_number_mask: str = Field("****1234", json_schema_extra={"example": "****1234"})
    currency: Literal["INR"] = Field("INR", json_schema_extra={"example": "INR"})
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


def _parse_account_type(type_str: str) -> AccountType:
    try:
        return AccountType(type_str.lower().strip())
    except ValueError as err:
        valid_types = [e.value for e in AccountType]
        raise BadRequestException(f"Invalid account_type '{type_str}'. Allowed values are: {valid_types}") from err


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(
    req: CreateAccountRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Create a new financial account (savings, checking, credit card). Requires terms consent."""
    account = Account(
        user_id=current_user.id,
        name=req.name,
        account_type=_parse_account_type(req.account_type),
        status=AccountStatus.ACTIVE,
        institution_name=req.institution_name,
        account_number_mask=req.account_number_mask,
        currency=req.currency,
        reported_balance=Decimal(str(req.initial_balance)),
        reported_balance_at=datetime.now(UTC),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return AccountResponse(
        id=str(account.id),
        user_id=str(account.user_id),
        name=account.name,
        account_type=account.account_type.value,
        institution_name=account.institution_name,
        account_number_mask=account.account_number_mask,
        currency=account.currency,
        current_balance=float(account.reported_balance),
        created_at=account.created_at.isoformat(),
    )


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[AccountResponse]:
    """Retrieve all accounts belonging to the authenticated user."""
    stmt = select(Account).where(Account.user_id == current_user.id).order_by(Account.created_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return [
        AccountResponse(
            id=str(acc.id),
            user_id=str(acc.user_id),
            name=acc.name,
            account_type=acc.account_type.value,
            institution_name=acc.institution_name,
            account_number_mask=acc.account_number_mask,
            currency=acc.currency,
            current_balance=float(acc.reported_balance),
            created_at=acc.created_at.isoformat(),
        )
        for acc in accounts
    ]


@router.post("/upload-statement", response_model=StatementUploadSummary)
async def upload_statement(
    req: UploadStatementRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> StatementUploadSummary:
    """Upload a bank statement (CSV or SMS text) with automatic deduplication, sanitization, and categorization."""
    try:
        acc_uuid = uuid.UUID(req.account_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Specified account does not exist or does not belong to you.") from err

    stmt = select(Account).where(Account.id == acc_uuid, Account.user_id == current_user.id)
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise NotFoundException("Specified account does not exist or does not belong to you.")

    is_sms = req.format.lower() == "sms"
    if is_sms:
        parsed_single = parse_sms_statement(req.content, str(account.id))
        parsed_txs = [parsed_single] if parsed_single else []
    else:
        parsed_txs = parse_csv_statement(req.content, str(account.id))

    if not parsed_txs:
        raise BadRequestException("Could not extract any valid transactions from the provided content.")

    # Create transaction import record
    tx_import = TransactionImport(
        user_id=current_user.id,
        account_id=account.id,
        source=TransactionSource.SMS if is_sms else TransactionSource.CSV_UPLOAD,
        status=ImportStatus.PROCESSING,
        total_parsed=len(parsed_txs),
        imported_count=0,
        duplicates_skipped=0,
        error_count=0,
        started_at=datetime.now(UTC),
    )
    db.add(tx_import)
    await db.flush()

    # Query existing fingerprints for this user to prevent duplicates
    fingerprints = [t["fingerprint"] for t in parsed_txs]
    existing_fp_stmt = select(Transaction.normalized_fingerprint).where(
        Transaction.user_id == current_user.id,
        Transaction.normalized_fingerprint.in_(fingerprints),
    )
    existing_fp_res = await db.execute(existing_fp_stmt)
    seen_fps = set(existing_fp_res.scalars().all())

    imported: list[dict[str, Any]] = []
    skipped_count = 0

    for tx in parsed_txs:
        fp = tx["fingerprint"]
        if fp in seen_fps:
            skipped_count += 1
            continue

        seen_fps.add(fp)
        t_type = TransactionType.CREDIT if tx["transaction_type"].lower() == "credit" else TransactionType.DEBIT
        amt_decimal = Decimal(str(tx["amount"]))

        new_tx_id = uuid.uuid4()
        new_tx = Transaction(
            id=new_tx_id,
            user_id=current_user.id,
            account_id=account.id,
            import_id=tx_import.id,
            transaction_date=tx["date"],
            amount=amt_decimal,
            transaction_type=t_type,
            category=tx.get("category", "Other"),
            description=tx.get("description", ""),
            description_cleaned=tx.get("description_cleaned", ""),
            merchant=tx.get("merchant"),
            normalized_merchant=tx.get("merchant", "").lower() if tx.get("merchant") else None,
            normalized_fingerprint=fp,
            source=TransactionSource.SMS if is_sms else TransactionSource.CSV_UPLOAD,
        )
        db.add(new_tx)
        await db.flush()

        # Update balance
        if t_type == TransactionType.CREDIT:
            account.reported_balance += amt_decimal
        else:
            account.reported_balance -= amt_decimal

        if t_type == TransactionType.DEBIT:
            await match_transaction_to_occurrence(db, current_user.id, new_tx)

        tx_record = {
            "id": str(new_tx.id),
            "account_id": str(account.id),
            "user_id": str(current_user.id),
            "date": tx["date"].isoformat() if isinstance(tx["date"], datetime) else str(tx["date"]),
            "amount": float(amt_decimal),
            "transaction_type": t_type.value,
            "category": new_tx.category,
            "description": new_tx.description,
            "description_cleaned": new_tx.description_cleaned,
            "merchant": new_tx.merchant,
        }
        imported.append(tx_record)

    tx_import.imported_count = len(imported)
    tx_import.duplicates_skipped = skipped_count
    tx_import.status = ImportStatus.COMPLETED
    tx_import.completed_at = datetime.now(UTC)

    await db.commit()

    return StatementUploadSummary(
        account_id=str(account.id),
        total_parsed=len(parsed_txs),
        imported_count=len(imported),
        duplicates_skipped=skipped_count,
        sample_imported=imported[:5],
    )


@router.get("/transactions")
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List transactions with optional filtering by account and category."""
    query = (
        select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.transaction_date.desc())
    )

    if account_id:
        try:
            acc_uuid = uuid.UUID(account_id)
            query = query.where(Transaction.account_id == acc_uuid)
        except (ValueError, TypeError):
            return []

    if category:
        query = query.where(Transaction.category.ilike(category))

    result = await db.execute(query)
    txs = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "account_id": str(t.account_id),
            "user_id": str(t.user_id),
            "date": t.transaction_date.isoformat(),
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
            "description": t.description,
            "description_cleaned": t.description_cleaned,
            "merchant": t.merchant,
        }
        for t in txs
    ]


@router.get("/cash-flow")
async def get_cash_flow(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Calculate monthly cash flow (inflow, outflow, net savings, savings rate)."""
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    result = await db.execute(stmt)
    tx_models = result.scalars().all()

    tx_dicts = [
        {
            "date": t.transaction_date,
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
        }
        for t in tx_models
    ]
    return compute_monthly_cash_flow(tx_dicts)


@router.get("/insights")
async def get_insights(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve personal finance insights: income volatility, balance runway, top spending categories."""
    tx_stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    tx_result = await db.execute(tx_stmt)
    tx_models = tx_result.scalars().all()

    acc_stmt = select(Account).where(Account.user_id == current_user.id)
    acc_result = await db.execute(acc_stmt)
    acc_models = acc_result.scalars().all()

    total_balance = sum(float(a.reported_balance) for a in acc_models)

    tx_dicts = [
        {
            "date": t.transaction_date,
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
        }
        for t in tx_models
    ]
    return compute_financial_insights(tx_dicts, current_balance=total_balance)
