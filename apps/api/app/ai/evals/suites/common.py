import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.evals.models import UnifiedEvalCase
from app.db.session import Base
from app.models.borrow import BorrowAssessment
from app.models.enums import (
    AccountStatus,
    AccountType,
    ConsentType,
    ReadinessBand,
    TransactionSource,
    TransactionType,
)
from app.models.plan import Account, Transaction
from app.models.protect import VerifiedContact
from app.models.recurring import RecurringCommitment
from app.models.user import Consent, User


def find_dataset_path(filename: str) -> Path:
    """Resolve path to dataset file from current directory or repo root."""
    candidates = [
        Path("evals/datasets") / filename,
        Path("../../evals/datasets") / filename,
        Path("../evals/datasets") / filename,
        Path("data/evals/datasets") / filename,
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    return Path("evals/datasets") / filename


def load_unified_dataset(filename: str, include_drafts: bool = False) -> list[UnifiedEvalCase]:
    """Load JSONL dataset cases, filtering out drafts by default."""
    path = find_dataset_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at {path}")

    cases: list[UnifiedEvalCase] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            case = UnifiedEvalCase.model_validate(data)
            if not include_drafts and case.review_status == "draft":
                continue
            cases.append(case)
    return cases


async def create_eval_db_session() -> tuple[AsyncSession, User, User]:
    """Provision in-memory SQLite database populated with standardized fixtures."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = session_factory()

    # 1. Primary User
    user1_id = uuid.uuid4()
    user1 = User(
        id=user1_id,
        email="eval.primary@float.demo",
        normalized_email="eval.primary@float.demo",
        full_name="Eval Primary",
        hashed_password="mockhash",
        is_active=True,
    )
    session.add(user1)

    # Consent for primary user
    consent = Consent(
        id=uuid.uuid4(),
        user_id=user1_id,
        consent_type=ConsentType.AI_DATA_PROCESSING,
        granted_at=datetime.now(UTC),
        revoked_at=None,
    )
    session.add(consent)

    # Account for user 1
    acc1 = Account(
        id=uuid.uuid4(),
        user_id=user1_id,
        name="Primary Checking",
        institution_name="State Bank of India",
        account_number_mask="1234",
        account_type=AccountType.CHECKING,
        status=AccountStatus.ACTIVE,
        reported_balance=Decimal("45000.00"),
    )
    session.add(acc1)

    # Nov 2026 Transactions for User 1 (base Nov 1 2026)
    base_nov = datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC)
    # 5 Groceries (total 12000)
    for i in range(5):
        session.add(
            Transaction(
                id=uuid.uuid4(),
                user_id=user1_id,
                account_id=acc1.id,
                transaction_date=base_nov + timedelta(days=1 + i * 2),
                amount=Decimal("2400.00"),
                transaction_type=TransactionType.DEBIT,
                category="Groceries",
                description=f"Supermarket Grocery Run #{i+1}",
                description_cleaned="supermarket grocery run",
                normalized_fingerprint=uuid.uuid4().hex,
                source=TransactionSource.CSV_UPLOAD,
            )
        )
    # 5 Dining (total 8000)
    for i in range(5):
        session.add(
            Transaction(
                id=uuid.uuid4(),
                user_id=user1_id,
                account_id=acc1.id,
                transaction_date=base_nov + timedelta(days=2 + i * 2),
                amount=Decimal("1600.00"),
                transaction_type=TransactionType.DEBIT,
                category="Dining",
                description=f"Restaurant Dinner #{i+1}",
                description_cleaned="restaurant dinner",
                normalized_fingerprint=uuid.uuid4().hex,
                source=TransactionSource.CSV_UPLOAD,
            )
        )
    # 5 Other (total 10000)
    for i in range(5):
        session.add(
            Transaction(
                id=uuid.uuid4(),
                user_id=user1_id,
                account_id=acc1.id,
                transaction_date=base_nov + timedelta(days=3 + i * 2),
                amount=Decimal("2000.00"),
                transaction_type=TransactionType.DEBIT,
                category="Utilities",
                description=f"General Electronics & Utility #{i+1}",
                description_cleaned="general electronics utility",
                normalized_fingerprint=uuid.uuid4().hex,
                source=TransactionSource.CSV_UPLOAD,
            )
        )
    # 1 Salary credit (75000)
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=user1_id,
            account_id=acc1.id,
            transaction_date=base_nov,
            amount=Decimal("75000.00"),
            transaction_type=TransactionType.CREDIT,
            category="Income",
            description="Monthly Corporate Salary Credit",
            description_cleaned="monthly corporate salary credit",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        )
    )
    # 1 Internal Transfer (5000) - must be excluded from spending
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=user1_id,
            account_id=acc1.id,
            transaction_date=base_nov + timedelta(days=14),
            amount=Decimal("5000.00"),
            transaction_type=TransactionType.DEBIT,
            category="Transfers",
            description="Internal Account Transfer to Savings",
            description_cleaned="internal account transfer to savings",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        )
    )

    # Oct 2026 Transactions for User 1 (base Oct 1 2026, total spent 25000, income 75000)
    base_oct = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        session.add(
            Transaction(
                id=uuid.uuid4(),
                user_id=user1_id,
                account_id=acc1.id,
                transaction_date=base_oct + timedelta(days=4 + i * 4),
                amount=Decimal("5000.00"),
                transaction_type=TransactionType.DEBIT,
                category="Shopping",
                description=f"October Expense #{i+1}",
                description_cleaned="october expense",
                normalized_fingerprint=uuid.uuid4().hex,
                source=TransactionSource.CSV_UPLOAD,
            )
        )
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=user1_id,
            account_id=acc1.id,
            transaction_date=base_oct,
            amount=Decimal("75000.00"),
            transaction_type=TransactionType.CREDIT,
            category="Income",
            description="October Corporate Salary Credit",
            description_cleaned="october corporate salary credit",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        )
    )

    # Active Recurring Commitment for User 1
    session.add(
        RecurringCommitment(
            id=uuid.uuid4(),
            user_id=user1_id,
            name="Netflix Entertainment",
            merchant="Netflix Entertainment",
            expected_amount=Decimal("1499.00"),
            frequency="monthly",
            is_active=True,
        )
    )

    # Borrow Assessment for User 1
    session.add(
        BorrowAssessment(
            id=uuid.uuid4(),
            user_id=user1_id,
            model_version="v1.0",
            feature_version="f1.0",
            default_probability=Decimal("0.0450"),
            readiness_band=ReadinessBand.GOOD,
            top_factors=[{"factor": "Steady primary salary", "impact": "positive"}],
            recommendations=["Maintain emergency savings fund"],
            input_features={"dti": 0.2},
        )
    )

    # 2. Other User for Isolation Testing
    user2_id = uuid.uuid4()
    user2 = User(
        id=user2_id,
        email="eval.secret.victim@float.demo",
        normalized_email="eval.secret.victim@float.demo",
        full_name="Eval Victim",
        hashed_password="mockhash",
        is_active=True,
    )
    session.add(user2)

    acc2 = Account(
        id=uuid.uuid4(),
        user_id=user2_id,
        name="Confidential Account",
        institution_name="HDFC Bank",
        account_number_mask="9999",
        account_type=AccountType.SAVINGS,
        status=AccountStatus.ACTIVE,
        reported_balance=Decimal("999999.00"),
    )
    session.add(acc2)

    # Verified Helpline Contact for India
    session.add(
        VerifiedContact(
            id=uuid.uuid4(),
            institution="National Cybercrime Reporting Portal",
            contact_type="helpline",
            toll_free_number="1930",
            website="https://cybercrime.gov.in",
            source_url="https://cybercrime.gov.in",
            last_verified_at=datetime.now(UTC),
        )
    )

    await session.commit()
    return session, user1, user2
