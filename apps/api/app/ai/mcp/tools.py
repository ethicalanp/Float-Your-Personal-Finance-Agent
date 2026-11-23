import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.agent.draft_service import create_complaint_draft
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.ai.tools.base import ToolContext
from app.ai.tools.executor import ToolExecutionBudget, ToolExecutor
from app.ai.tools.registry import default_registry
from app.services.scam_detector import analyze_scam_message
from app.services.verified_contacts import VERIFIED_DIRECTORY, search_verified_contacts

# ============================================================================
# 1. get_cash_flow
# ============================================================================


class CashFlowToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date = Field(description="Start date (inclusive) in YYYY-MM-DD format")
    end_date: date = Field(description="End date (inclusive) in YYYY-MM-DD format")
    bucket: Literal["daily", "weekly", "monthly"] = Field(
        default="monthly", description="Time aggregation bucket: daily, weekly, or monthly"
    )


async def execute_cash_flow(
    args: CashFlowToolInput,
    user_id: uuid.UUID,
    session: AsyncSession | Session,
    executor: ToolExecutor | None = None,
) -> dict[str, Any]:
    exec_inst = executor or ToolExecutor(registry=default_registry)
    ctx = ToolContext(
        user_id=user_id,
        request_id=f"mcp_{uuid.uuid4().hex[:8]}",
        session=session,
    )
    res = await exec_inst.execute(
        name="get_cash_flow",
        arguments=args.model_dump(),
        context=ctx,
        budget=ToolExecutionBudget(),
    )
    return {
        "ok": res.ok,
        "tool": "get_cash_flow",
        "data": res.data,
        "facts": [f.model_dump() for f in res.facts],
        "period": res.period,
        "row_count": res.row_count,
    }


# ============================================================================
# 2. check_scam_message (Existing Protect scam rules; works without LLM)
# ============================================================================


class CheckScamInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The suspicious message, SMS, WhatsApp text, or email body to analyze (max 1000 chars)",
    )


async def execute_check_scam_message(
    args: CheckScamInput,
) -> dict[str, Any]:
    """Analyze suspicious message using deterministic Protect scam rules."""
    analysis = analyze_scam_message(args.message)
    return {
        "ok": True,
        "tool": "check_scam_message",
        "is_scam": analysis.get("is_scam", False),
        "risk_score": float(analysis.get("risk_score", 0.0)),
        "risk_tier": analysis.get("risk_tier", "SAFE"),
        "language_detected": analysis.get("language_detected", "en"),
        "matched_indicators": analysis.get("matched_indicators", []),
        "helpline": "1930",
        "official_portal": "https://cybercrime.gov.in",
        "guidance": (
            "Never share OTPs, passwords, or approve unknown collect requests. "
            "Report cyber fraud immediately at 1930 or cybercrime.gov.in."
        ),
    }


# ============================================================================
# 3. get_borrow_readiness (Indicative readiness only; unavailable state on error)
# ============================================================================


class BorrowReadinessToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of_date: date | None = Field(
        default=None, description="Optional target date for readiness evaluation in YYYY-MM-DD format"
    )


async def execute_borrow_readiness(
    args: BorrowReadinessToolInput,
    user_id: uuid.UUID,
    session: AsyncSession | Session,
    executor: ToolExecutor | None = None,
) -> dict[str, Any]:
    exec_inst = executor or ToolExecutor(registry=default_registry)
    ctx = ToolContext(
        user_id=user_id,
        request_id=f"mcp_{uuid.uuid4().hex[:8]}",
        session=session,
    )
    try:
        res = await exec_inst.execute(
            name="get_borrow_readiness",
            arguments={"as_of_date": args.as_of_date} if args.as_of_date else {},
            context=ctx,
            budget=ToolExecutionBudget(),
        )
        data = res.data
        if data.get("status") == "insufficient_data":
            return {
                "ok": True,
                "tool": "get_borrow_readiness",
                "status": "unavailable",
                "readiness_band": "unavailable",
                "message": "Indicative borrow assessment is unavailable due to insufficient transaction history.",
                "disclaimer": "Indicative readiness only; Float never invents credit scores or approves credit.",
            }
        return {
            "ok": True,
            "tool": "get_borrow_readiness",
            "status": "available",
            "data": data,
            "facts": [f.model_dump() for f in res.facts],
            "disclaimer": "Indicative readiness only; Float never invents credit scores or approves credit.",
        }
    except Exception:
        return {
            "ok": True,
            "tool": "get_borrow_readiness",
            "status": "unavailable",
            "readiness_band": "unavailable",
            "message": "Indicative borrow readiness model is currently unavailable.",
            "disclaimer": "Indicative readiness only; Float never invents credit scores or approves credit.",
        }


# ============================================================================
# 4. draft_complaint (Deterministic template, returns draft only)
# ============================================================================


class DraftComplaintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_name: str = Field(description="Name of the financial institution or bank")
    account_number_mask: str = Field(description="Last 4 digits or masked identifier of the victim's account")
    transaction_reference: str = Field(description="Bank UTR, UPI transaction ID, or reference number")
    transaction_amount: float = Field(ge=0.01, description="Amount debited in the unauthorized transaction")
    incident_date: str | None = Field(
        default=None, description="Date of transaction in YYYY-MM-DD or DD-Month-YYYY format"
    )
    description: str = Field(default="", max_length=2000, description="Brief narrative of the fraud event")


async def execute_draft_complaint(
    args: DraftComplaintInput,
    user_id: uuid.UUID,
    session: AsyncSession | Session | None = None,
) -> dict[str, Any]:
    """Create formal complaint draft in pending_confirmation status."""
    return await create_complaint_draft(
        user_id=user_id,
        bank_name=args.bank_name,
        account_number_mask=args.account_number_mask,
        transaction_reference=args.transaction_reference,
        transaction_amount=args.transaction_amount,
        incident_date=args.incident_date,
        description=args.description,
        session=session,
    )


# ============================================================================
# 5. get_verified_contacts (Verified directory only, category filter)
# ============================================================================


class VerifiedCategoryEnum(str):
    GOVERNMENT = "government"
    PUBLIC_BANK = "public_bank"
    PRIVATE_BANK = "private_bank"
    TELECOM = "telecom"
    ALL = "all"


class GetVerifiedContactsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["government", "public_bank", "private_bank", "telecom", "all"] = Field(
        default="all", description="Category filter for verified institutions"
    )
    search_query: str | None = Field(default=None, max_length=100, description="Optional institution keyword to match")


async def execute_get_verified_contacts(
    args: GetVerifiedContactsInput,
) -> dict[str, Any]:
    """Retrieve verified helpline and grievance directory entries."""
    if args.search_query:
        contacts = search_verified_contacts(args.search_query)
    else:
        contacts = list(VERIFIED_DIRECTORY)

    category_map = {
        "government": "Government & Law Enforcement",
        "public_bank": "Public Sector Bank",
        "private_bank": "Private Sector Bank",
        "telecom": "Telecom",
    }

    if args.category != "all":
        target_cat = category_map.get(args.category, "")
        contacts = [c for c in contacts if c.get("category") == target_cat]

    sanitized = []
    for c in contacts:
        sanitized.append({
            "institution": c.get("institution"),
            "category": c.get("category"),
            "toll_free_number": c.get("toll_free_number"),
            "website": c.get("website"),
            "fraud_reporting_email": c.get("fraud_reporting_email"),
            "sms_block_code": c.get("sms_block_code"),
            "priority_notice": c.get("priority_notice"),
        })

    return {
        "ok": True,
        "tool": "get_verified_contacts",
        "count": len(sanitized),
        "contacts": sanitized,
    }


# ============================================================================
# 6. search_knowledge (Retrieval only, cited snippets, query capped)
# ============================================================================


class SearchKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Search inquiry for regulatory, banking, or cyber fraud guidance (max 200 characters)",
    )
    language: str = Field(default="en", description="Target language: en, ml, or manglish")
    top_k: int = Field(default=3, ge=1, le=5, description="Number of top regulatory snippets to retrieve (1 to 5)")


async def execute_search_knowledge(
    args: SearchKnowledgeInput,
    session: AsyncSession | Session,
    retriever: HybridRetriever | None = None,
) -> dict[str, Any]:
    """Retrieve official regulatory excerpts with citations. Strict query length cap."""
    r = retriever or HybridRetriever(
        session=session,
        embedder=get_embedder(),
        config=RetrievalConfig(return_size=args.top_k),
    )
    evidence = await r.retrieve(args.query)

    snippets = []
    for idx, chunk in enumerate(evidence.chunks[: args.top_k]):
        snippets.append({
            "citation_alias": f"E{idx + 1}",
            "title": chunk.title,
            "publisher": chunk.publisher,
            "section": chunk.heading_path,
            "source_url": chunk.source_url,
            "text_snippet": chunk.text[:300].strip(),
            "score": round(chunk.fused_score, 4),
        })

    return {
        "ok": True,
        "tool": "search_knowledge",
        "query": args.query,
        "result_count": len(snippets),
        "passed_min_evidence": evidence.passed_min_evidence,
        "degraded": evidence.degraded,
        "snippets": snippets,
    }
