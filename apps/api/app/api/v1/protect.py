import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.errors import NotFoundException
from app.core.security import CurrentUser, get_current_user
from app.services.complaint_drafter import draft_fraud_complaint
from app.services.data_sanitizer import mask_sensitive_data
from app.services.scam_detector import analyze_scam_message
from app.services.verified_contacts import (
    get_all_verified_contacts,
    search_verified_contacts,
)

router = APIRouter(prefix="/protect", tags=["Protect — Financial Scam Detection & Recovery"])

# In-memory storage for testability & local operations
_CHECK_LOGS_DB: dict[str, dict[str, Any]] = {}
_SAMPLES_DB: list[dict[str, Any]] = []
_RECOVERY_CASES_DB: dict[str, dict[str, Any]] = {}
_AUDIT_TRAIL_DB: list[dict[str, Any]] = []


def record_audit(action: str, resource_type: str, resource_id: str | None = None, user_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    _AUDIT_TRAIL_DB.append({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata or {},
        "created_at": datetime.now(UTC).isoformat(),
    })


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


@router.post("/check")
async def check_scam_message(
    req: ScamCheckRequest,
    current_user: CurrentUser | None = Depends(lambda: None),
) -> dict[str, Any]:
    """Analyze suspicious message for fraud/phishing indicators across English, Malayalam, and Manglish."""
    result = analyze_scam_message(req.message)
    check_id = str(uuid.uuid4())
    masked_msg = mask_sensitive_data(req.message)

    log_entry = {
        "id": check_id,
        "user_id": current_user.user_id if current_user else None,
        "message_masked": masked_msg,
        "result": result,
        "created_at": datetime.now(UTC).isoformat(),
        "feedback": None,
    }
    _CHECK_LOGS_DB[check_id] = log_entry

    record_audit(
        action="SCAM_CHECK_EXECUTED",
        resource_type="scam_check",
        resource_id=check_id,
        user_id=current_user.user_id if current_user else None,
        metadata={"risk_tier": result["risk_tier"], "language": result["language"], "risk_score": result["risk_score"]},
    )

    return {
        "check_id": check_id,
        "analysis": result,
        "message_masked": masked_msg,
    }


@router.post("/check/feedback")
async def submit_check_feedback(
    req: CheckFeedbackRequest,
    current_user: CurrentUser | None = Depends(lambda: None),
) -> dict[str, Any]:
    """Capture user accuracy feedback to refine detection rules and active learning datasets."""
    check = _CHECK_LOGS_DB.get(req.check_id)
    if not check:
        raise NotFoundException("Specified scam check record not found.")

    check["feedback"] = {
        "is_accurate": req.is_accurate,
        "notes": req.notes,
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    record_audit(
        action="FEEDBACK_RECORDED",
        resource_type="scam_check",
        resource_id=req.check_id,
        user_id=current_user.user_id if current_user else None,
        metadata={"is_accurate": req.is_accurate},
    )

    return {"status": "feedback_recorded", "check_id": req.check_id}


@router.post("/samples", status_code=201)
async def submit_scam_sample(
    sample: ScamSampleSubmission,
    current_user: CurrentUser | None = Depends(lambda: None),
) -> dict[str, Any]:
    """Submit a real labeled Malayalam, Manglish, or English scam example for daily dataset curation."""
    sample_id = str(uuid.uuid4())
    record = {
        "id": sample_id,
        "text": mask_sensitive_data(sample.text),
        "language": sample.language.lower(),
        "is_scam": sample.is_scam,
        "scam_type": sample.scam_type,
        "source": sample.source,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _SAMPLES_DB.append(record)

    record_audit(
        action="DATASET_SAMPLE_ADDED",
        resource_type="scam_sample",
        resource_id=sample_id,
        user_id=current_user.user_id if current_user else None,
        metadata={"language": sample.language, "scam_type": sample.scam_type},
    )

    return {"status": "sample_added", "sample_id": sample_id}


@router.get("/samples")
async def list_scam_samples(
    language: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Retrieve curated multilingual scam samples for inspection and model training."""
    samples = _SAMPLES_DB
    if language:
        samples = [s for s in samples if s["language"] == language.lower()]
    return samples[-limit:]


@router.post("/recovery-cases", status_code=201)
async def create_recovery_case(
    req: CreateRecoveryCaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Initiate a first-hour fraud recovery case with an actionable recovery checklist."""
    case_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    masked_summary = mask_sensitive_data(req.incident_summary)

    checklist = [
        {"step": "call_1930", "title": "Call 1930 National Cyber Helpline", "status": "pending"},
        {"step": "freeze_bank", "title": "Contact Bank Fraud Helpline to block card & account", "status": "pending"},
        {"step": "change_credentials", "title": "Reset NetBanking, UPI MPIN, and email passwords", "status": "pending"},
        {"step": "save_evidence", "title": "Preserve transaction SMS, call logs, and screenshots", "status": "pending"},
    ]

    case = {
        "id": case_id,
        "user_id": current_user.user_id,
        "scam_type": req.scam_type,
        "amount_lost": req.amount_lost,
        "platform": req.platform,
        "incident_summary_masked": masked_summary,
        "status": "reported",
        "checklist": checklist,
        "created_at": now,
        "updated_at": now,
    }
    _RECOVERY_CASES_DB[case_id] = case

    record_audit(
        action="RECOVERY_CASE_CREATED",
        resource_type="recovery_case",
        resource_id=case_id,
        user_id=current_user.user_id,
        metadata={"scam_type": req.scam_type, "amount_lost": req.amount_lost},
    )

    return case


@router.get("/recovery-cases")
async def list_recovery_cases(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all recovery cases for the authenticated user."""
    return [c for c in _RECOVERY_CASES_DB.values() if c["user_id"] == current_user.user_id]


@router.patch("/recovery-cases/{case_id}")
async def update_recovery_case(
    case_id: str,
    req: UpdateRecoveryCaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Update progress on recovery checklist or case status."""
    case = _RECOVERY_CASES_DB.get(case_id)
    if not case or case["user_id"] != current_user.user_id:
        raise NotFoundException("Recovery case not found.")

    if req.status:
        case["status"] = req.status
    if req.completed_step:
        for item in case["checklist"]:
            if item["step"] == req.completed_step:
                item["status"] = "completed"

    case["updated_at"] = datetime.now(UTC).isoformat()
    return case


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
    current_user: CurrentUser = Depends(get_current_user),
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

    record_audit(
        action="COMPLAINT_DRAFTED",
        resource_type="complaint_draft",
        user_id=current_user.user_id,
        metadata={"bank": req.bank_name, "amount": req.transaction_amount},
    )

    return draft


@router.get("/audit-trail")
async def get_audit_trail(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve the immutable audit log of all security and fraud recovery actions for the user."""
    return [a for a in _AUDIT_TRAIL_DB if a.get("user_id") == current_user.user_id or a.get("user_id") is None]
