import os

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.core.dependencies import get_db

_embedder_instance: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    """Return active embedding service. In tests or without sentence_transformers, returns FakeEmbedder."""
    global _embedder_instance
    if _embedder_instance is not None:
        return _embedder_instance

    app_env = os.environ.get("PFA_APP_ENV", "development").lower()
    if app_env == "test":
        _embedder_instance = FakeEmbedder()
        return _embedder_instance

    try:
        import sentence_transformers  # noqa: F401

        from app.ai.rag.embedder.local import LocalEmbedder

        _embedder_instance = LocalEmbedder()
    except Exception:
        _embedder_instance = FakeEmbedder()

    return _embedder_instance


def set_embedder(embedder: BaseEmbedder | None) -> None:
    """Override active embedder (useful for tests)."""
    global _embedder_instance
    _embedder_instance = embedder


def get_knowledge_service(
    db: AsyncSession = Depends(get_db),
    gateway: LLMGateway = Depends(get_llm_gateway),
    embedder: BaseEmbedder = Depends(get_embedder),
) -> KnowledgeAnswerService:
    """Dependency provider for KnowledgeAnswerService."""
    retriever = HybridRetriever(session=db, embedder=embedder, config=RetrievalConfig())
    return KnowledgeAnswerService(session=db, retriever=retriever, gateway=gateway)
