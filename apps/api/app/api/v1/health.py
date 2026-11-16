from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["healthy"]


@router.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check whether the API application is running."""
    return HealthResponse(status="healthy")