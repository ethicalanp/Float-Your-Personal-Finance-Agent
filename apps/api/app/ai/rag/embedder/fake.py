import hashlib
import math
import random

from app.ai.rag.embedder.base import BaseEmbedder


class FakeEmbedder(BaseEmbedder):
    """Deterministic, zero-network fake embedder for tests producing unit-normalized 768d vectors."""

    def __init__(
        self,
        dimension: int = 768,
        model_name: str = "intfloat/multilingual-e5-base",
        fail_next_n: int = 0,
    ) -> None:
        super().__init__(dimension=dimension, model_name=model_name)
        self.fail_next_n = fail_next_n
        self.call_count = 0

    def _generate_vector(self, text: str) -> list[float]:
        self.call_count += 1
        if self.fail_next_n > 0:
            self.fail_next_n -= 1
            raise RuntimeError("Simulated transient embedder failure")

        # Derive a stable 64-bit integer seed from SHA-256 of text
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], byteorder="big")

        rng = random.Random(seed)
        # Generate pseudo-random normal values
        raw = [rng.gauss(0.0, 1.0) for _ in range(self.dimension)]

        # L2 normalization to unit length
        norm = math.sqrt(sum(x * x for x in raw))
        if norm == 0.0:
            return [0.0] * self.dimension
        return [round(x / norm, 6) for x in raw]

    def embed_passage(self, text: str) -> list[float]:
        # Emulate ADR-001 "passage: " prefixing
        prefixed = f"passage: {text}"
        return self._generate_vector(prefixed)

    def embed_passages(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        return [self.embed_passage(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        # Emulate ADR-001 "query: " prefixing
        prefixed = f"query: {query}"
        return self._generate_vector(prefixed)
