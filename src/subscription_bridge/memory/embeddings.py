from __future__ import annotations

import hashlib
import math
from typing import Any


class EmbeddingProvider:
    dim: int = 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]


class HashEmbeddingProvider(EmbeddingProvider):
    dim: int = 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = text.lower().split()
        if not words:
            return vec

        for word in words:
            h = hashlib.md5(word.encode("utf-8")).digest()
            for i in range(self.dim):
                vec[i] += (h[i % 16] / 255.0) * 2.0 - 1.0

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    dim: int = 384

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            self._loaded = True
        except ImportError:
            raise RuntimeError("sentence-transformers not installed")
        except Exception as e:
            raise RuntimeError(f"Failed to load model {self._model_name}: {e}")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self._load()
        result = self._model.encode(texts, show_progress_bar=False)
        return result.tolist()  # type: ignore[no-any-return]


def create_embedding_provider(provider_name: str = "hash") -> EmbeddingProvider:
    if provider_name == "sentence_transformer":
        try:
            return SentenceTransformerEmbeddingProvider()
        except Exception:
            pass
    return HashEmbeddingProvider()
