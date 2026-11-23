"""Float Knowledge RAG Subsystem: Ingestion, Chunking, Embeddings & Retrieval."""

from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.embedder.local import LocalEmbedder
from app.ai.rag.manifest import load_manifest
from app.ai.rag.models import DocumentChunk, Manifest, ManifestSource
from app.ai.rag.pipeline import run_ingestion_pipeline
from app.ai.rag.repository import KnowledgeRepository

__all__ = [
    "BaseEmbedder",
    "FakeEmbedder",
    "LocalEmbedder",
    "Manifest",
    "ManifestSource",
    "DocumentChunk",
    "KnowledgeRepository",
    "load_manifest",
    "run_ingestion_pipeline",
]
