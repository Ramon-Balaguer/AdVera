"""Embedding provider boundary (spec §5 Embeddings; ADR 0001; brain-embeddings-provider.md).

EmbeddingProvider
  -> BgeM3Provider   local BAAI/bge-m3 through sentence-transformers, exactly 1024 dimensions

The model loads lazily in the Brain worker (optional `brain` extra). Vectors are L2
normalized for cosine search and validated against the schema dimension; anything else fails
explicitly instead of being stored.
"""

import threading
from typing import Protocol

import numpy as np

from app.models import EMBEDDING_DIMENSION


class EmbeddingUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EmbeddingProvider(Protocol):
    name: str
    model: str
    model_version: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return one normalized EMBEDDING_DIMENSION row per text. Blocking."""
        ...


def validate_vectors(vectors: np.ndarray, count: int) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.shape != (count, EMBEDDING_DIMENSION) or not np.isfinite(vectors).all():
        raise EmbeddingUnavailable("EMBEDDING_INVALID")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class BgeM3Provider:
    name = "sentence-transformers"

    def __init__(self, model: str, device: str, cache_dir: str, batch_size: int = 16) -> None:
        self.model = model
        self.model_version = "1"
        self.device = device
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            try:
                import torch  # noqa: F401
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise EmbeddingUnavailable("EMBEDDINGS_NOT_INSTALLED") from error
            try:
                self._model = SentenceTransformer(
                    self.model, device=self.device, cache_folder=self.cache_dir
                )
            except Exception as error:
                raise EmbeddingUnavailable("EMBEDDING_MODEL_UNAVAILABLE") from error
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            model = self._load()
            try:
                vectors = model.encode(
                    texts,
                    batch_size=self.batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            except Exception as error:
                raise EmbeddingUnavailable("EMBEDDING_FAILED") from error
        return validate_vectors(vectors, len(texts))
