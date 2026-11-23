from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.dependencies import require_consent
from app.core.errors import ServiceUnavailableException, UnprocessableException
from app.models.enums import ConsentType
from app.models.user import User
from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION
from app.services.synthetic_borrow_demo import evaluate_synthetic_borrow_demo
from app.services.synthetic_scam_demo import evaluate_synthetic_scam_demo

router = APIRouter(prefix="/ml-demo", tags=["Experimental ML demos"])


class SyntheticBorrowDemoRequest(BaseModel):
    feature_version: str
    monthly_inflow_avg: float | None = None
    income_volatility_cov: float | None = None
    income_sources_count: float | None = None
    debt_to_income_ratio: float | None = None
    expense_to_income_ratio: float | None = None
    fixed_expense_ratio: float | None = None
    savings_rate_pct: float | None = None
    buffer_runway_months: float | None = None
    min_balance_ratio: float | None = None
    negative_balance_events: float | None = None


class SyntheticScamDemoRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


@router.post("/borrow")
async def predict_synthetic_borrow_demo(
    body: SyntheticBorrowDemoRequest,
    request: Request,
    _current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
) -> dict[str, Any]:
    """Run the isolated synthetic Borrow demo; this does not create a real assessment."""
    settings = request.app.state.settings
    if not settings.enable_synthetic_ml_demos:
        raise ServiceUnavailableException("Experimental synthetic ML demos are disabled.")
    features = body.model_dump(include=set(FEATURE_COLUMNS) | {"feature_version"})
    if body.feature_version != FEATURE_VERSION:
        raise UnprocessableException(f"Synthetic Borrow demo requires feature version {FEATURE_VERSION}.")
    try:
        return evaluate_synthetic_borrow_demo(features, settings.synthetic_borrow_demo_model_path)
    except ValueError as exc:
        raise UnprocessableException(str(exc)) from exc


@router.post("/scam")
async def predict_synthetic_scam_demo(
    body: SyntheticScamDemoRequest,
    request: Request,
    _current_user: User = Depends(require_consent(ConsentType.AI_DATA_PROCESSING)),
) -> dict[str, Any]:
    """Run the isolated synthetic scam demo without storing or logging the message."""
    settings = request.app.state.settings
    if not settings.enable_synthetic_ml_demos:
        raise ServiceUnavailableException("Experimental synthetic ML demos are disabled.")
    try:
        return evaluate_synthetic_scam_demo(body.message, settings.synthetic_scam_demo_model_path)
    except ValueError as exc:
        raise UnprocessableException(str(exc)) from exc
