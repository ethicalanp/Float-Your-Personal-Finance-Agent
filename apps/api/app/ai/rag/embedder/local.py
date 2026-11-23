from typing import Any, cast

from app.ai.rag.embedder.base import BaseEmbedder


class LocalEmbedder(BaseEmbedder):
    """Local SentenceTransformer embedder running on CPU (e.g. intfloat/multilingual-e5-base).

    Automatically applies the required 'passage: ' and 'query: ' prefixes per ADR-001.
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        dimension: int = 768,
        device: str = "cpu",
    ) -> None:
        super().__init__(dimension=dimension, model_name=model_name)
        self.device = device
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            import os
            import sys

            if sys.platform == "win32":
                torch_lib = os.path.join(sys.prefix, "Lib", "site-packages", "torch", "lib")
                if os.path.exists(torch_lib):
                    try:
                        os.add_dll_directory(torch_lib)
                    except Exception:
                        pass
            try:
                from sentence_transformers import SentenceTransformer

                print(
                    f"[Embedder] Initializing model '{self.model_name}' on {self.device}... "
                    f"(checking local cache or downloading if needed)",
                    flush=True,
                )
                try:
                    self._model = SentenceTransformer(
                        self.model_name, device=self.device, local_files_only=True
                    )
                    print(f"[Embedder] Model '{self.model_name}' loaded from local cache.", flush=True)
                except Exception:
                    print(
                        f"[Embedder] Model '{self.model_name}' not cached locally. Downloading model weights...",
                        flush=True,
                    )
                    self._model = SentenceTransformer(self.model_name, device=self.device)
                    print(f"[Embedder] Download complete. Model '{self.model_name}' ready.", flush=True)
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is not installed. To run the real local embedding model, "
                    'install the optional AI dependencies via: pip install -e ".[ai]"'
                ) from e
        return self._model

    def embed_passage(self, text: str) -> list[float]:
        model = self._get_model()
        prefixed = f"passage: {text}"
        vec = model.encode(prefixed, normalize_embeddings=True)
        return cast(list[float], vec.tolist())

    def embed_passages(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        model = self._get_model()
        prefixed_texts = [f"passage: {t}" for t in texts]
        vecs = model.encode(prefixed_texts, batch_size=batch_size, normalize_embeddings=True)
        return cast(list[list[float]], vecs.tolist())

    def embed_query(self, query: str) -> list[float]:
        model = self._get_model()
        prefixed = f"query: {query}"
        vec = model.encode(prefixed, normalize_embeddings=True)
        return cast(list[float], vec.tolist())
