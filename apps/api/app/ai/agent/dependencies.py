from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.orchestrator import AssistantOrchestrator
from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.db.session import get_db

_orchestrator: AssistantOrchestrator | None = None


def set_orchestrator(orchestrator: AssistantOrchestrator | None) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def get_orchestrator(
    session: AsyncSession = Depends(get_db),
    gateway: LLMGateway = Depends(get_llm_gateway),
) -> AssistantOrchestrator:
    if _orchestrator is not None:
        return _orchestrator
    return AssistantOrchestrator(session=session, gateway=gateway)
