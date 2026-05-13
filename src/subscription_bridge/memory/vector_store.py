from __future__ import annotations

import json
import math
from pathlib import Path

from subscription_bridge.memory.models import DocumentChunk, SearchResult


class VectorStore:
    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []
        self._embeddings: list[list[float]] = []

    @property
    def size(self) -> int:
        return len(self._chunks)

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must match")
        self._chunks.extend(chunks)
        self._embeddings.extend(embeddings)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[SearchResult]:
        if not self._chunks:
            return []

        scores: list[tuple[int, float]] = []
        for i, emb in enumerate(self._embeddings):
            score = self._cosine_similarity(query_embedding, emb)
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top = scores[:top_k]

        results: list[SearchResult] = []
        for idx, score in top:
            chunk = self._chunks[idx]
            preview = chunk.text[:200].replace("\n", " ")
            results.append(SearchResult(
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=round(score, 4),
                match_type="semantic",
                preview=preview,
                symbols=chunk.symbols,
                chunk_id=chunk.chunk_id,
            ))

        return results

    def save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)

        chunks_data = []
        for c in self._chunks:
            chunks_data.append({
                "file_path": c.file_path,
                "language": c.language,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "text": c.text,
                "chunk_id": c.chunk_id,
                "symbols": c.symbols,
                "imports": c.imports,
                "file_hash": c.file_hash,
            })

        (index_dir / "chunks.json").write_text(
            json.dumps(chunks_data, ensure_ascii=False), encoding="utf-8"
        )

        import numpy as np
        np.save(str(index_dir / "embeddings.npy"), np.array(self._embeddings, dtype=np.float32))

    def load(self, index_dir: Path) -> None:
        chunks_path = index_dir / "chunks.json"
        embeddings_path = index_dir / "embeddings.npy"

        if not chunks_path.exists() or not embeddings_path.exists():
            raise FileNotFoundError(f"No index found in {index_dir}")

        chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
        self._chunks = [DocumentChunk(**c) for c in chunks_data]

        import numpy as np
        self._embeddings = np.load(str(embeddings_path)).tolist()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(av * bv for av, bv in zip(a, b, strict=False))
        na = math.sqrt(sum(v * v for v in a))
        nb = math.sqrt(sum(v * v for v in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
