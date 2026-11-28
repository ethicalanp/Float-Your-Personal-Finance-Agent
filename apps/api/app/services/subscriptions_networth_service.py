import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.plan import Transaction
from app.models.recurring import RecurringCommitment
from app.models.subscriptions_networth import NetWorthItem, NetWorthSnapshot, SubscriptionLeakDecision

STALE_DAYS_THRESHOLD = 30
SMALL_SUBSCRIPTION_PAISE = 50_000  # ₹500
TRIAL_MAX_PAISE = 19_900  # ₹199


class SubscriptionLeakItem(BaseModel):
    leak_key: str
    merchant: str
    rules_triggered: list[str]
    monthly_amount_paise: int
    annual_cost_paise: int
    decision: Literal["undecided", "keep", "cancel"] = "undecided"
    explanation: str


class SubscriptionLeaksResponse(BaseModel):
    total_leaks: int
    estimated_yearly_savings_paise: int
    potential_yearly_savings_paise: int
    leaks: list[SubscriptionLeakItem] = Field(default_factory=list)


class NetWorthItemOut(BaseModel):
    id: str
    name: str
    item_type: Literal["asset", "liability"]
    category: str
    amount_paise: int
    version: int
    valued_at: str
    is_stale: bool
    days_since_update: int


class NetWorthSnapshotOut(BaseModel):
    id: str
    snapshot_date: str
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int


class NetWorthOverviewResponse(BaseModel):
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int
    is_negative: bool
    stale_count: int
    items: list[NetWorthItemOut] = Field(default_factory=list)
    snapshots: list[NetWorthSnapshotOut] = Field(default_factory=list)


async def _exec(session: AsyncSession | Session, stmt: Any) -> Any:
    if isinstance(session, AsyncSession):
        return await session.execute(stmt)
    return session.execute(stmt)


def _norm_merchant(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    tokens = [t for t in cleaned.split() if t not in {"india", "subscription", "autopay", "upi", "payment"}]
    return " ".join(tokens[:2]) if tokens else "unknown"


def _annualize_paise(c: RecurringCommitment) -> tuple[int, int]:
    amt = int(round(float(c.expected_amount or 0) * 100))
    if c.frequency == "weekly":
        return int(round(amt * 52 / 12)), amt * 52
    if c.frequency == "quarterly":
        return int(round(amt / 3)), amt * 4
    if c.frequency == "yearly":
        return int(round(amt / 12)), amt
    return amt, amt * 12


async def compute_subscription_leaks(
    session: AsyncSession | Session,
    user_id: uuid.UUID,
) -> SubscriptionLeaksResponse:
    """Detect subscription leaks deterministically and deduplicate across rules per merchant key."""
    c_res = await _exec(
        session,
        select(RecurringCommitment).where(
            RecurringCommitment.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
        ),
    )
    commitments = list(c_res.scalars().all())

    t_res = await _exec(
        session,
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.DEBIT,
        )
        .order_by(Transaction.transaction_date.asc()),
    )
    debits = list(t_res.scalars().all())

    d_res = await _exec(
        session,
        select(SubscriptionLeakDecision).where(SubscriptionLeakDecision.user_id == user_id),
    )
    decisions = {d.leak_key: d.decision for d in d_res.scalars().all()}

    # Map normalized merchant -> candidate leak record (deduplicated across rules)
    leak_map: dict[str, dict[str, Any]] = {}

    def _add_rule(key: str, merchant: str, rule: str, monthly_p: int, annual_p: int, reason: str) -> None:
        if key not in leak_map:
            leak_map[key] = {
                "merchant": merchant,
                "rules": [],
                "monthly_p": monthly_p,
                "annual_p": annual_p,
                "reasons": [],
            }
        rec = leak_map[key]
        if rule not in rec["rules"]:
            rec["rules"].append(rule)
            rec["reasons"].append(reason)
        rec["monthly_p"] = max(rec["monthly_p"], monthly_p)
        rec["annual_p"] = max(rec["annual_p"], annual_p)

    # 1. Analyze recurring commitments (duplicates, annual renewals, small recurring)
    by_merchant_c: dict[str, list[RecurringCommitment]] = {}
    for c in commitments:
        mk = _norm_merchant(c.merchant or c.name)
        by_merchant_c.setdefault(mk, []).append(c)

        m_p, a_p = _annualize_paise(c)
        if c.frequency == "yearly":
            _add_rule(mk, c.name, "annual_renewal", m_p, a_p, f"Annual renewal of ₹{a_p / 100:,.0f}/yr.")
        if m_p <= SMALL_SUBSCRIPTION_PAISE and "sub" in (c.category or "").lower():
            _add_rule(mk, c.name, "small_recurring", m_p, a_p, f"Small recurring charge of ₹{m_p / 100:,.0f}/mo.")

    for mk, items in by_merchant_c.items():
        if len(items) >= 2:
            m_p, a_p = _annualize_paise(items[0])
            _add_rule(
                mk,
                items[0].name,
                "duplicate",
                m_p,
                a_p,
                f"{len(items)} overlapping commitments match '{mk}'.",
            )

    # 2. Analyze debit transactions (price increases, trial-to-paid, duplicate same-month debits)
    by_merchant_tx: dict[str, list[Transaction]] = {}
    for t in debits:
        mk = _norm_merchant(t.description)
        by_merchant_tx.setdefault(mk, []).append(t)

    for mk, txs in by_merchant_tx.items():
        if len(txs) < 2:
            continue
        amounts = [int(round(float(t.amount) * 100)) for t in txs]
        first_amt, last_amt = amounts[0], amounts[-1]
        # Trial-to-paid: small initial debit <= ₹199 followed by >= 3x larger charge within 45 days
        if first_amt <= TRIAL_MAX_PAISE and last_amt >= first_amt * 3:
            delta_days = (txs[-1].transaction_date - txs[0].transaction_date).days
            if 0 <= delta_days <= 45:
                _add_rule(
                    mk,
                    txs[-1].description[:40],
                    "trial_to_paid",
                    last_amt,
                    last_amt * 12,
                    f"Converted from ₹{first_amt / 100:,.0f} trial to ₹{last_amt / 100:,.0f}/mo.",
                )
        # Price increase: > 5% jump from previous charge
        elif len(amounts) >= 2 and amounts[-2] > TRIAL_MAX_PAISE and last_amt > int(amounts[-2] * 1.05):
            _add_rule(
                mk,
                txs[-1].description[:40],
                "price_increase",
                last_amt,
                last_amt * 12,
                f"Charge increased from ₹{amounts[-2] / 100:,.0f} to ₹{last_amt / 100:,.0f}.",
            )
        # Same-month duplicate debits of identical amount
        month_pairs: dict[tuple[str, int], int] = {}
        for t, amt in zip(txs, amounts, strict=True):
            m_key = (t.transaction_date.strftime("%Y-%m"), amt)
            month_pairs[m_key] = month_pairs.get(m_key, 0) + 1
        if any(cnt >= 2 for cnt in month_pairs.values()):
            _add_rule(
                mk,
                txs[-1].description[:40],
                "duplicate",
                last_amt,
                last_amt * 12,
                f"Multiple identical debits (₹{last_amt / 100:,.0f}) in the same month.",
            )

    leaks: list[SubscriptionLeakItem] = []
    est_savings = 0
    pot_savings = 0
    for key in sorted(leak_map):
        rec = leak_map[key]
        dec_raw = decisions.get(key, "undecided")
        dec: Literal["undecided", "keep", "cancel"] = (
            dec_raw if dec_raw in ("keep", "cancel") else "undecided"
        )  # type: ignore[assignment]
        if dec == "cancel":
            est_savings += rec["annual_p"]
        if dec != "keep":
            pot_savings += rec["annual_p"]
        leaks.append(
            SubscriptionLeakItem(
                leak_key=key,
                merchant=rec["merchant"],
                rules_triggered=rec["rules"],
                monthly_amount_paise=rec["monthly_p"],
                annual_cost_paise=rec["annual_p"],
                decision=dec,
                explanation=" ".join(rec["reasons"]),
            )
        )

    return SubscriptionLeaksResponse(
        total_leaks=len(leaks),
        estimated_yearly_savings_paise=est_savings,
        potential_yearly_savings_paise=pot_savings,
        leaks=leaks,
    )


async def compute_net_worth_overview(
    session: AsyncSession | Session,
    user_id: uuid.UUID,
    now_utc: datetime | None = None,
) -> NetWorthOverviewResponse:
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    i_res = await _exec(
        session,
        select(NetWorthItem)
        .where(NetWorthItem.user_id == user_id)
        .order_by(NetWorthItem.item_type.asc(), NetWorthItem.name.asc()),
    )
    items = list(i_res.scalars().all())

    s_res = await _exec(
        session,
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user_id)
        .order_by(NetWorthSnapshot.snapshot_date.asc(), NetWorthSnapshot.created_at.asc()),
    )
    snaps = list(s_res.scalars().all())

    assets_p = 0
    liab_p = 0
    stale_count = 0
    out_items: list[NetWorthItemOut] = []

    for it in items:
        amt = int(it.amount_paise)
        if it.item_type == "asset":
            assets_p += amt
        else:
            liab_p += amt
        val_dt = it.valued_at if it.valued_at.tzinfo else it.valued_at.replace(tzinfo=UTC)
        days_old = max(0, (now - val_dt).days)
        is_stale = days_old >= STALE_DAYS_THRESHOLD
        if is_stale:
            stale_count += 1
        out_items.append(
            NetWorthItemOut(
                id=str(it.id),
                name=it.name,
                item_type=it.item_type,  # type: ignore[arg-type]
                category=it.category,
                amount_paise=amt,
                version=int(it.version),
                valued_at=val_dt.isoformat(),
                is_stale=is_stale,
                days_since_update=days_old,
            )
        )

    nw_p = assets_p - liab_p
    out_snaps = [
        NetWorthSnapshotOut(
            id=str(s.id),
            snapshot_date=s.snapshot_date.isoformat(),
            total_assets_paise=int(s.total_assets_paise),
            total_liabilities_paise=int(s.total_liabilities_paise),
            net_worth_paise=int(s.net_worth_paise),
        )
        for s in snaps
    ]

    return NetWorthOverviewResponse(
        total_assets_paise=assets_p,
        total_liabilities_paise=liab_p,
        net_worth_paise=nw_p,
        is_negative=nw_p < 0,
        stale_count=stale_count,
        items=out_items,
        snapshots=out_snaps,
    )
