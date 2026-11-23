from abc import ABC, abstractmethod

from app.ai.rag.models import ParsedDocument


class BaseParser(ABC):
    """Abstract interface for document parsers."""

    @abstractmethod
    def parse(self, content_bytes: bytes, filename: str | None = None) -> ParsedDocument:
        """Parse raw document bytes into a structured ParsedDocument."""
        pass
