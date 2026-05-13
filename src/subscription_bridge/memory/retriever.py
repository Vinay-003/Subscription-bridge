from __future__ import annotations

import re
from typing import Any

from subscription_bridge.memory.embeddings import EmbeddingProvider, HashEmbeddingProvider
from subscription_bridge.memory.models import IndexData, SearchResult
from subscription_bridge.memory.vector_store import VectorStore


class Retriever:
    def __init__(
        self,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._embedder = embedder or HashEmbeddingProvider()

    def retrieve(
        self,
        query: str,
        index_data: IndexData,
        top_k: int = 10,
    ) -> list[SearchResult]:
        if not index_data.chunks:
            return []

        query_embedding = self._embedder.embed_query(query)

        store = VectorStore()
        if index_data.embeddings:
            store.add(index_data.chunks, index_data.embeddings)
        else:
            embeddings = self._embedder.embed_texts([c.text for c in index_data.chunks])
            store.add(index_data.chunks, embeddings)

        semantic_results = store.search(query_embedding, top_k=top_k * 2)

        keyword_scores = self._keyword_search(query, index_data)
        symbol_scores = self._symbol_search(query, index_data)

        combined = self._merge_results(semantic_results, keyword_scores, symbol_scores, index_data.chunks, top_k)

        return combined[:top_k]

    def _keyword_search(
        self,
        query: str,
        index_data: IndexData,
    ) -> dict[str, float]:
        terms = set(re.findall(r"\w+", query.lower()))
        if not terms:
            return {}

        scores: dict[str, float] = {}
        for chunk in index_data.chunks:
            text_lower = chunk.text.lower()
            match_count = sum(1 for t in terms if t in text_lower)
            if match_count > 0:
                scores[chunk.chunk_id] = match_count / len(terms)
        return scores

    def _symbol_search(
        self,
        query: str,
        index_data: IndexData,
    ) -> dict[str, float]:
        query_lower = query.lower()
        scores: dict[str, float] = {}

        for chunk in index_data.chunks:
            for sym in chunk.symbols:
                if sym.lower() == query_lower:
                    scores[chunk.chunk_id] = max(scores.get(chunk.chunk_id, 0), 1.0)
                elif sym.lower() in query_lower or query_lower in sym.lower():
                    scores[chunk.chunk_id] = max(scores.get(chunk.chunk_id, 0), 0.8)

        return scores

    def _merge_results(
        self,
        semantic: list[SearchResult],
        keyword_scores: dict[str, float],
        symbol_scores: dict[str, float],
        chunks: list[Any],
        top_k: int,
    ) -> list[SearchResult]:
        combined: dict[str, SearchResult] = {}

        for result in semantic:
            combined[result.chunk_id] = result

        for chunk_id, kw_score in keyword_scores.items():
            if chunk_id in combined:
                combined[chunk_id].score = max(combined[chunk_id].score, kw_score)
                if combined[chunk_id].match_type == "semantic":
                    combined[chunk_id].match_type = "keyword+semantic"
                else:
                    combined[chunk_id].match_type = "keyword"
            else:
                combined[chunk_id] = SearchResult(
                    chunk_id=chunk_id,
                    score=kw_score * 0.7,
                    match_type="keyword",
                )

        for chunk_id, sym_score in symbol_scores.items():
            if chunk_id in combined:
                boost = sym_score * 0.3
                combined[chunk_id].score += boost
                if "symbol" not in combined[chunk_id].match_type:
                    combined[chunk_id].match_type += "+symbol"
            else:
                combined[chunk_id] = SearchResult(
                    chunk_id=chunk_id,
                    score=sym_score * 0.5,
                    match_type="symbol",
                )

        results = sorted(combined.values(), key=lambda r: r.score, reverse=True)

        chunk_map = {c.chunk_id: c for c in chunks}
        chunk_map.update({c.chunk_id: c for c in (semantic or [])})
        for r in results:
            if r.chunk_id in chunk_map:
                src = chunk_map[r.chunk_id]
                r.file_path = src.file_path or r.file_path
                r.start_line = src.start_line or r.start_line
                r.end_line = src.end_line or r.end_line
                r.symbols = src.symbols or r.symbols
                if hasattr(src, 'preview'):
                    r.preview = src.preview or r.preview
                elif hasattr(src, 'text'):
                    r.preview = (src.text or "")[:200]

        return results[:top_k]

    @staticmethod
    def search_by_vector(
        store: VectorStore,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[SearchResult]:
        return store.search(query_embedding, top_k=top_k)
