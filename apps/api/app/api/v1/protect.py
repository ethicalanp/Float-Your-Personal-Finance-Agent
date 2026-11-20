import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import BadRequestException, NotFoundException
from app.models.enums import (
    AuditActor,
    CaseStatus,
    ConsentType,
    LanguageCode,
    RiskTier,
)
from app.models.protect import (
    AuditTrail,
    RecoveryCase,
    ScamCheckLog,
    ScamSample,
)
from app.models.user import User
from app.services.complaint_drafter import draft_fraud_complaint
from app.services.data_sanitizer import mask_sensitive_data
from app.services.scam_detector import analyze_scam_message
from app.services.verified_contacts import (
    get_all_verified_contacts,
    search_verified_contacts,
)

router = APIRouter(prefix="/protect", tags=["Protect — Financial Scam Detection & Recovery"])


class ScamCheckRequest(BaseModel):
    message: str = Field(..., description="Message text in English, Malayalam, or Manglish to evaluate")


class CheckFeedbackRequest(BaseModel):
    check_id: str
    is_accurate: bool
    notes: str | None = None


class ScamSampleSubmission(BaseModel):
    text: str
    language: str = Field(..., json_schema_extra={"example": "manglish"})  # en, ml, manglish
    is_scam: bool = True
    scam_type: str = Field("phishing", json_schema_extra={"example": "electricity_bill_scam"})
    source: str = "user_submission"


class CreateRecoveryCaseRequest(BaseModel):
    scam_type: str = Field("upi_fraud", json_schema_extra={"example": "upi_fraud"})
    amount_lost: float = Field(0.0, json_schema_extra={"example": 25000.0})
    platform: str = Field("WhatsApp", json_schema_extra={"example": "WhatsApp"})
    incident_summary: str = Field(..., description="Chronological explanation of what happened")


class UpdateRecoveryCaseRequest(BaseModel):
    status: str | None = None  # reported, in_progress, resolved
    completed_step: str | None = None


class DraftComplaintRequest(BaseModel):
    victim_name: str
    bank_name: str
    account_number_mask: str
    transaction_reference: str
    transaction_amount: float
    scam_type: str = "Unauthorized Electronic Transaction / Fraud"
    incident_description: str = ""


def _parse_language_code(lang_str: str) -> LanguageCode:
    l_str = lang_str.lower().strip()
    if l_str in ("ml", "malayalam"):
        return LanguageCode.ML
    elif l_str in ("manglish",):
        return LanguageCode.MANGLISH
    elif l_str in ("en", "english"):
        return LanguageCode.EN
    valid_langs = [language.value for language in LanguageCode]
    raise BadRequestException(f"Invalid language '{lang_str}'. Allowed values are: {valid_langs}")


def _parse_risk_tier(tier_str: str) -> RiskTier:
    try:
        return RiskTier(tier_str.upper().strip())
    except ValueError as err:
        valid_tiers = [t.value for t in RiskTier]
        raise BadRequestException(
            f"Invalid risk_tier '{tier_str}'. Allowed values are: {valid_tiers}"
        ) from err


def _record_audit_db(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    user_id: uuid.UUID | None = None,
    actor: AuditActor = AuditActor.USER,
    metadata: dict[str, Any] | None = None,
) -> None:
    audit_entry = AuditTrail(
        user_id=user_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        metadata_json=metadata or {},
    )
    db.add(audit_entry)


@router.post("/check")
async def check_scam_message(
    req: ScamCheckRequest,
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Analyze suspicious message for fraud/phishing indicators across English, Malayalam, and Manglish."""
    result = analyze_scam_message(req.message)
    masked_msg = mask_sensitive_data(req.message)

    log_entry = ScamCheckLog(
        user_id=current_user.id,
        message_masked=masked_msg,
        language_detected=_parse_language_code(result.get("language", "en")),
        risk_score=Decimal(str(result.get("risk_score", 0.0))),
        risk_tier=_parse_risk_tier(result.get("risk_tier", "SAFE")),
        indicators=result.get("indicators", []),
        model_version="rules_v1.0",
        is_scam=result.get("risk_tier", "SAFE") in ("HIGH", "CRITICAL"),
    )
    db.add(log_entry)
    await db.flush()

    _record_audit_db(
        db=db,
        action="SCAM_CHECK_EXECUTED",
        resource_type="scam_check",
        resource_id=str(log_entry.id),
        user_id=current_user.id,
        metadata={
            "risk_tier": result.get("risk_tier"),
            "language": result.get("language"),
            "risk_score": result.get("risk_score"),
        },
    )
    await db.commit()

    return {
        "check_id": str(log_entry.id),
        "analysis": result,
        "message_masked": masked_msg,
    }


@router.post("/check/feedback")
async def submit_check_feedback(
    req: CheckFeedbackRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Capture user accuracy feedback to refine detection rules and active learning datasets."""
    try:
        check_uuid = uuid.UUID(req.check_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Specified scam check record not found.") from err

    stmt = select(ScamCheckLog).where(
        ScamCheckLog.id == check_uuid,
        ScamCheckLog.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    check = result.scalar_one_or_none()
    if not check:
        raise NotFoundException("Specified scam check record not found.")

    check.user_feedback_accurate = req.is_accurate
    check.user_feedback_notes = mask_sensitive_data(req.notes) if req.notes else None

    _record_audit_db(
        db=db,
        action="FEEDBACK_RECORDED",
        resource_type="scam_check",
        resource_id=str(check.id),
        user_id=current_user.id,
        metadata={"is_accurate": req.is_accurate},
    )
    await db.commit()

    return {"status": "feedback_recorded", "check_id": str(check.id)}


@router.post("/samples", status_code=201)
async def submit_scam_sample(
    sample: ScamSampleSubmission,
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a real labeled scam example for dataset curation. Requires AI data contribution consent."""
    masked_text = mask_sensitive_data(sample.text)
    text_hash = hashlib.sha256(masked_text.encode("utf-8")).hexdigest()

    # Deduplicate sample by text_hash
    stmt = select(ScamSample).where(ScamSample.text_hash == text_hash)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return {"status": "sample_already_exists"}

    new_sample = ScamSample(
        text=masked_text,
        text_hash=text_hash,
        language=_parse_language_code(sample.language),
        is_scam=sample.is_scam,
        scam_type=sample.scam_type,
        source=sample.source,
        labeled_by=current_user.id,
    )
    db.add(new_sample)
    await db.flush()

    _record_audit_db(
        db=db,
        action="DATASET_SAMPLE_ADDED",
        resource_type="scam_sample",
        resource_id=str(new_sample.id),
        user_id=current_user.id,
        metadata={"language": sample.language, "scam_type": sample.scam_type},
    )
    await db.commit()

    return {"status": "sample_added", "sample_id": str(new_sample.id)}


@router.get("/samples")
async def list_scam_samples(
    language: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve user's own contributed scam samples. Cross-tenant sample text is never exposed."""
    stmt = (
        select(ScamSample)
        .where(ScamSample.labeled_by == current_user.id)
        .order_by(ScamSample.created_at.desc())
        .limit(limit)
    )
    if language:
        stmt = stmt.where(ScamSample.language == _parse_language_code(language))

    result = await db.execute(stmt)
    samples = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "text": s.text,
            "language": s.language.value,
            "is_scam": s.is_scam,
            "scam_type": s.scam_type,
            "source": s.source,
            "created_at": s.created_at.isoformat(),
        }
        for s in samples
    ]


@router.post("/recovery-cases", status_code=201)
async def create_recovery_case(
    req: CreateRecoveryCaseRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Initiate a first-hour fraud recovery case with an actionable recovery checklist."""
    masked_summary = mask_sensitive_data(req.incident_summary)

    checklist = [
        {"step": "call_1930", "title": "Call 1930 National Cyber Helpline", "status": "pending"},
        {"step": "freeze_bank", "title": "Contact Bank Fraud Helpline to block card & account", "status": "pending"},
        {"step": "change_credentials", "title": "Reset NetBanking, UPI MPIN, and email passwords", "status": "pending"},
        {"step": "save_evidence", "title": "Preserve transaction SMS, call logs, and screenshots", "status": "pending"},
    ]

    case = RecoveryCase(
        user_id=current_user.id,
        scam_type=req.scam_type,
        amount_lost=Decimal(str(req.amount_lost)),
        platform=req.platform,
        incident_summary_masked=masked_summary,
        status=CaseStatus.REPORTED,
        steps_completed=checklist,
    )
    db.add(case)
    await db.flush()

    _record_audit_db(
        db=db,
        action="RECOVERY_CASE_CREATED",
        resource_type="recovery_case",
        resource_id=str(case.id),
        user_id=current_user.id,
        metadata={"scam_type": req.scam_type, "amount_lost": req.amount_lost},
    )
    await db.commit()

    return {
        "id": str(case.id),
        "user_id": str(case.user_id),
        "scam_type": case.scam_type,
        "amount_lost": float(case.amount_lost),
        "platform": case.platform,
        "incident_summary_masked": case.incident_summary_masked,
        "status": case.status.value,
        "checklist": case.steps_completed,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


@router.get("/recovery-cases")
async def list_recovery_cases(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all recovery cases for the authenticated user."""
    stmt = select(RecoveryCase).where(RecoveryCase.user_id == current_user.id).order_by(RecoveryCase.created_at.desc())
    result = await db.execute(stmt)
    cases = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "scam_type": c.scam_type,
            "amount_lost": float(c.amount_lost),
            "platform": c.platform,
            "incident_summary_masked": c.incident_summary_masked,
            "status": c.status.value,
            "checklist": c.steps_completed,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in cases
    ]


@router.patch("/recovery-cases/{case_id}")
async def update_recovery_case(
    case_id: str,
    req: UpdateRecoveryCaseRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update progress on recovery checklist or case status."""
    try:
        case_uuid = uuid.UUID(case_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Recovery case not found.") from err

    stmt = select(RecoveryCase).where(
        RecoveryCase.id == case_uuid,
        RecoveryCase.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    case = result.scalar_one_or_none()
    if not case:
        raise NotFoundException("Recovery case not found.")

    if req.status:
        try:
            case.status = CaseStatus(req.status.lower().strip())
        except ValueError as err:
            valid_statuses = [s.value for s in CaseStatus]
            raise BadRequestException(
                f"Invalid status '{req.status}'. Allowed values are: {valid_statuses}"
            ) from err

    if req.completed_step:
        updated_checklist = []
        for item in case.steps_completed:
            copied = dict(item)
            if copied.get("step") == req.completed_step:
                copied["status"] = "completed"
            updated_checklist.append(copied)
        case.steps_completed = updated_checklist

    case.updated_at = datetime.now(UTC)
    await db.commit()

    return {
        "id": str(case.id),
        "user_id": str(case.user_id),
        "scam_type": case.scam_type,
        "amount_lost": float(case.amount_lost),
        "platform": case.platform,
        "incident_summary_masked": case.incident_summary_masked,
        "status": case.status.value,
        "checklist": case.steps_completed,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


@router.get("/verified-contacts")
async def get_verified_contacts(
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve verified, official contacts for banks, National Cyber Crime Helpline (1930), and portals."""
    if query:
        return search_verified_contacts(query)
    return get_all_verified_contacts()


@router.post("/draft-complaint")
async def generate_complaint_draft(
    req: DraftComplaintRequest,
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a formal bank and cybercell dispute grievance notice using verified institution contacts."""
    draft = draft_fraud_complaint(
        victim_name=req.victim_name,
        bank_name=req.bank_name,
        account_number_mask=req.account_number_mask,
        transaction_reference=req.transaction_reference,
        transaction_amount=req.transaction_amount,
        scam_type=req.scam_type,
        description=req.incident_description,
    )

    _record_audit_db(
        db=db,
        action="COMPLAINT_DRAFTED",
        resource_type="complaint_draft",
        user_id=current_user.id,
        metadata={"bank": req.bank_name, "amount": req.transaction_amount},
    )
    await db.commit()

    return draft


@router.get("/audit-trail")
async def get_audit_trail(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve the immutable audit log strictly scoped to the authenticated user."""
    stmt = select(AuditTrail).where(AuditTrail.user_id == current_user.id).order_by(AuditTrail.created_at.desc())
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "user_id": str(e.user_id) if e.user_id else None,
            "actor": e.actor.value,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "metadata": e.metadata_json,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
