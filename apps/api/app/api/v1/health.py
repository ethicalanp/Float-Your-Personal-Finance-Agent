from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.sms_provider import Msg91SmsProvider, get_sms_provider

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["healthy"]


class ReadinessResponse(BaseModel):
    ready: bool
    status: str
    details: str
    checks: dict[str, Any]


@router.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check whether the API application is running."""
    return HealthResponse(status="healthy")


@router.get("/ready", tags=["Health"], response_model=ReadinessResponse)
async def readiness_check(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ReadinessResponse:
    """Readiness probe checking subsystem configurations including SMS provider."""
    checks: dict[str, Any] = {}
    is_ready = True
    failure_reasons: list[str] = []

    # Check SMS Provider readiness
    if settings.sms_provider == "msg91":
        provider = get_sms_provider(settings)
        if isinstance(provider, Msg91SmsProvider) and not provider.is_configured():
            is_ready = False
            checks["sms_provider"] = "misconfigured"
            failure_reasons.append("MSG91 provider credentials not configured")
        else:
            checks["sms_provider"] = "configured"
    elif settings.sms_provider == "fake" and settings.app_env != "development":
        is_ready = False
        checks["sms_provider"] = "misconfigured"
        failure_reasons.append("Fake SMS provider is not permitted in non-development environments")
    else:
        checks["sms_provider"] = settings.sms_provider

    if not is_ready:
        response.status_code = 503

    return ReadinessResponse(
        ready=is_ready,
        status="ready" if is_ready else "not_ready",
        details="; ".join(failure_reasons) if failure_reasons else "All readiness checks passed",
        checks=checks,
    )
