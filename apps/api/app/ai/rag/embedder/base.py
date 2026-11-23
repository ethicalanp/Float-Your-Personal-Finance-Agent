from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Abstract interface for dense embedding generation."""

    def __init__(self, dimension: int = 768, model_name: str = "intfloat/multilingual-e5-base") -> None:
        self.dimension = dimension
        self.model_name = model_name

    @abstractmethod
    def embed_passage(self, text: str) -> list[float]:
        """Embed a single passage for indexing (applying model-specific passage prefixes)."""
        pass

    @abstractmethod
    def embed_passages(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        """Embed multiple passages in batches."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a user search query (applying model-specific query prefixes)."""
        pass
