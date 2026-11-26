"""Synthetic Demo Data Seeder for Float MVP.

All seeded records are purely synthetic, explicitly marked "NOT REAL", and used
solely for local UI testing, integration verification, and staging demonstrations.
"""

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

# Ensure apps/api is in pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.enums import (
    AccountStatus,
    AccountType,
    CaseStatus,
    ConsentType,
    RiskTier,
    TransactionType,
)
from app.models.plan import Account, Transaction, TransactionImport
from app.models.protect import RecoveryCase
from app.models.user import Consent, User

DEMO_EMAIL = "demo@float.internal"
DEMO_PASSWORD = "DemoPassword123!"
DEMO_NAME = "Demo User (Synthetic Data - Not Real)"


async def seed_demo_data(database_url: str | None = None) -> dict[str, str | int]:
    """Seed synthetic demo user, accounts, transactions, and recovery cases."""
    if not database_url:
        settings = get_settings()
        database_url = settings.database_url

    if not database_url:
        raise RuntimeError("No database URL provided or found in PFA_DATABASE_URL.")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = datetime.now(UTC)

    async with session_factory() as session:
        # Check if demo user already exists; if so, clean up previous demo data
        existing = await session.execute(
            select(User).where(User.normalized_email == DEMO_EMAIL.lower().strip())
        )
        old_user = existing.scalar_one_or_none()
        if old_user:
            print(f"[*] Removing existing demo user: {DEMO_EMAIL}")
            u_id = old_user.id
            # Clean up dependent records
            await session.execute(delete(RecoveryCase).where(RecoveryCase.user_id == u_id))
            await session.execute(delete(Transaction).where(Transaction.user_id == u_id))
            await session.execute(delete(TransactionImport).where(TransactionImport.user_id == u_id))
            await session.execute(delete(Account).where(Account.user_id == u_id))
            await session.execute(delete(Consent).where(Consent.user_id == u_id))
            await session.execute(delete(User).where(User.id == u_id))
            await session.commit()

        # 1. Create Demo User
        demo_user = User(
            id=uuid.uuid4(),
            email=DEMO_EMAIL,
            normalized_email=DEMO_EMAIL.lower().strip(),
            hashed_password=hash_password(DEMO_PASSWORD),
            full_name=DEMO_NAME,
            is_active=True,
            created_at=now,
        )
        session.add(demo_user)
        await session.flush()

        # 2. Grant Required Consents
        consents = [
            Consent(
                id=uuid.uuid4(),
                user_id=demo_user.id,
                consent_type=ConsentType.TERMS,
                consent_version="v1.0",
                granted_at=now,
            ),
            Consent(
                id=uuid.uuid4(),
                user_id=demo_user.id,
                consent_type=ConsentType.AI_DATA_PROCESSING,
                consent_version="v1.0",
                granted_at=now,
            ),
        ]
        session.add_all(consents)

        # 3. Create Synthetic Accounts
        salary_acct = Account(
            id=uuid.uuid4(),
            user_id=demo_user.id,
            name="HDFC Salary Account (Synthetic)",
            account_type=AccountType.SAVINGS,
            status=AccountStatus.ACTIVE,
            currency="INR",
            current_balance=Decimal("45200.00"),
            created_at=now,
        )
        savings_acct = Account(
            id=uuid.uuid4(),
            user_id=demo_user.id,
            name="SBI Savings Account (Synthetic)",
            account_type=AccountType.SAVINGS,
            status=AccountStatus.ACTIVE,
            currency="INR",
            current_balance=Decimal("125000.00"),
            created_at=now,
        )
        session.add_all([salary_acct, savings_acct])
        await session.flush()

        # 4. Create Statement Import Record
        stmt_import = TransactionImport(
            id=uuid.uuid4(),
            user_id=demo_user.id,
            account_id=salary_acct.id,
            filename="synthetic_bank_statement_nov2026.csv",
            status="completed",
            row_count=8,
            error_count=0,
            imported_at=now,
        )
        session.add(stmt_import)
        await session.flush()

        # 5. Create Synthetic Transactions
        sample_txs = [
            ("Salary Credit Tech Corp (Synthetic)", Decimal("75000.00"), TransactionType.CREDIT, 25, "income"),
            ("House Rent Owner Transfer (Synthetic)", Decimal("22000.00"), TransactionType.DEBIT, 24, "housing"),
            ("Electricity Bill KSEB (Synthetic)", Decimal("2450.00"), TransactionType.DEBIT, 20, "utilities"),
            ("Swiggy Online Food Order (Synthetic)", Decimal("450.00"), TransactionType.DEBIT, 18, "food"),
            ("UPI Grocery Mart Supermarket (Synthetic)", Decimal("1850.00"), TransactionType.DEBIT, 15, "groceries"),
            ("SIP Mutual Fund Investment (Synthetic)", Decimal("10000.00"), TransactionType.DEBIT, 10, "investment"),
            ("Jio Fibre Broadband Bill (Synthetic)", Decimal("999.00"), TransactionType.DEBIT, 5, "utilities"),
            ("Freelance Consulting Payment (Synthetic)", Decimal("15000.00"), TransactionType.CREDIT, 2, "income"),
        ]

        tx_models = []
        for desc, amount, tx_type, days_ago, cat in sample_txs:
            tx_models.append(
                Transaction(
                    id=uuid.uuid4(),
                    user_id=demo_user.id,
                    account_id=salary_acct.id,
                    import_id=stmt_import.id,
                    amount=amount,
                    currency="INR",
                    direction=tx_type,
                    description=desc,
                    category=cat,
                    posted_at=now - timedelta(days=days_ago),
                    created_at=now - timedelta(days=days_ago),
                )
            )
        session.add_all(tx_models)

        # 6. Create Synthetic Recovery Case (Protect)
        rec_case = RecoveryCase(
            id=uuid.uuid4(),
            user_id=demo_user.id,
            scam_type="upi_phishing_qr",
            amount_lost=Decimal("15000.00"),
            currency="INR",
            platform="WhatsApp",
            status=CaseStatus.ACTION_TAKEN,
            checklist={
                "reported_to_1930": True,
                "reported_to_bank": True,
                "cybercrime_portal_ack": "CR2026110091",
                "upi_reference_captured": True,
            },
            notes="Synthetic demo case: user clicked a fake electricity disconnection QR code.",
            created_at=now - timedelta(days=3),
        )
        session.add(rec_case)

        await session.commit()

    await engine.dispose()

    return {
        "status": "seeded",
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "accounts_created": 2,
        "transactions_created": len(sample_txs),
        "recovery_cases_created": 1,
    }


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    res = asyncio.run(seed_demo_data(url))
    print(f"[+] Seeding completed successfully: {res}")
