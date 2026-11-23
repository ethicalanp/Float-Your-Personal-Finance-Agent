from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import NotFoundException, UnprocessableException
from app.models.borrow import BorrowAssessment
from app.models.enums import AuditActor, ConsentType, ReadinessBand
from app.models.protect import AuditTrail
from app.models.user import User
from app.services.borrow_features import extract_borrow_features
from app.services.borrow_model import evaluate_borrow_readiness
from app.services.borrow_recommender import (
    LEGAL_DISCLAIMER,
    generate_borrow_recommendations,
)

router = APIRouter(prefix="/borrow", tags=["Borrow — Alternative Credit Readiness"])


class FactorItem(BaseModel):
    feature: str
    label: str
    value: float | None
    impact: float
    direction: str
    description: str


class RecommendationItem(BaseModel):
    category: str
    title: str
    action: str


class BorrowAssessmentResponse(BaseModel):
    id: str
    user_id: str
    model_version: str
    feature_version: str
    default_probability: float
    readiness_band: str
    top_factors: list[FactorItem]
    positive_factors: list[FactorItem]
    negative_factors: list[FactorItem]
    recommendations: list[RecommendationItem]
    input_features: dict[str, Any]
    legal_disclaimer: str
    created_at: str


@router.post("/assess", response_model=BorrowAssessmentResponse, status_code=201)
async def assess_borrow_readiness(
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> BorrowAssessmentResponse:
    """Run an alternative credit readiness assessment using cash flow underwriting and recurring payment discipline."""
    # 1. Feature extraction
    features = await extract_borrow_features(db=db, user_id=current_user.id)
    if features["transaction_count"] == 0:
        raise UnprocessableException(
            "Import a bank statement with transaction history before requesting a borrow-readiness assessment."
        )

    # 2. Load the versioned model and calculate calibrated risk plus TreeSHAP explanations.
    evaluation = evaluate_borrow_readiness(features)
    readiness_band: ReadinessBand = evaluation["readiness_band"]
    default_prob: float = evaluation["default_probability"]
    factors: list[dict[str, Any]] = evaluation["top_factors"]
    positive_factors: list[dict[str, Any]] = evaluation["positive_factors"]
    negative_factors: list[dict[str, Any]] = evaluation["negative_factors"]

    # 3. Recommendations
    recommendations = generate_borrow_recommendations(readiness_band, negative_factors, features)

    # 4. Save to DB
    assessment = BorrowAssessment(
        user_id=current_user.id,
        model_version=evaluation["model_version"],
        feature_version=evaluation["feature_version"],
        default_probability=Decimal(str(default_prob)),
        readiness_band=readiness_band,
        top_factors=factors,
        recommendations=recommendations,
        input_features=features,
    )
    db.add(assessment)
    await db.flush()
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="borrow_assessment_created",
            resource_type="borrow_assessment",
            resource_id=str(assessment.id),
            metadata_json={
                "model_version": evaluation["model_version"],
                "feature_version": evaluation["feature_version"],
                "readiness_band": readiness_band.value,
            },
        )
    )
    await db.commit()
    await db.refresh(assessment)

    return BorrowAssessmentResponse(
        id=str(assessment.id),
        user_id=str(assessment.user_id),
        model_version=assessment.model_version,
        feature_version=assessment.feature_version,
        default_probability=float(assessment.default_probability),
        readiness_band=assessment.readiness_band.value,
        top_factors=[FactorItem(**f) for f in assessment.top_factors],
        positive_factors=[FactorItem(**f) for f in positive_factors],
        negative_factors=[FactorItem(**f) for f in negative_factors],
        recommendations=[RecommendationItem(**r) for r in assessment.recommendations],
        input_features=assessment.input_features,
        legal_disclaimer=LEGAL_DISCLAIMER,
        created_at=assessment.created_at.isoformat(),
    )


@router.get("/latest", response_model=BorrowAssessmentResponse)
async def get_latest_assessment(
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> BorrowAssessmentResponse:
    """Retrieve the latest indicative credit readiness assessment for the authenticated user."""
    stmt = (
        select(BorrowAssessment)
        .where(BorrowAssessment.user_id == current_user.id)
        .order_by(BorrowAssessment.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise NotFoundException("No credit readiness assessments found. Run /borrow/assess to generate one.")

    return BorrowAssessmentResponse(
        id=str(assessment.id),
        user_id=str(assessment.user_id),
        model_version=assessment.model_version,
        feature_version=assessment.feature_version,
        default_probability=float(assessment.default_probability),
        readiness_band=assessment.readiness_band.value,
        top_factors=[FactorItem(**f) for f in assessment.top_factors],
        positive_factors=[FactorItem(**f) for f in assessment.top_factors if f["direction"] == "positive"],
        negative_factors=[FactorItem(**f) for f in assessment.top_factors if f["direction"] == "negative"],
        recommendations=[RecommendationItem(**r) for r in assessment.recommendations],
        input_features=assessment.input_features,
        legal_disclaimer=LEGAL_DISCLAIMER,
        created_at=assessment.created_at.isoformat(),
    )


@router.get("/history", response_model=list[BorrowAssessmentResponse])
async def get_assessment_history(
    current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
    db: AsyncSession = Depends(get_db),
) -> list[BorrowAssessmentResponse]:
    """Retrieve the historical sequence of credit readiness assessments to track improvement over time."""
    stmt = (
        select(BorrowAssessment)
        .where(BorrowAssessment.user_id == current_user.id)
        .order_by(BorrowAssessment.created_at.desc())
    )
    result = await db.execute(stmt)
    assessments = result.scalars().all()

    return [
        BorrowAssessmentResponse(
            id=str(a.id),
            user_id=str(a.user_id),
            model_version=a.model_version,
            feature_version=a.feature_version,
            default_probability=float(a.default_probability),
            readiness_band=a.readiness_band.value,
            top_factors=[FactorItem(**f) for f in a.top_factors],
            positive_factors=[FactorItem(**f) for f in a.top_factors if f["direction"] == "positive"],
            negative_factors=[FactorItem(**f) for f in a.top_factors if f["direction"] == "negative"],
            recommendations=[RecommendationItem(**r) for r in a.recommendations],
            input_features=a.input_features,
            legal_disclaimer=LEGAL_DISCLAIMER,
            created_at=a.created_at.isoformat(),
        )
        for a in assessments
    ]
