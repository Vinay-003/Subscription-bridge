from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.memory.embeddings import HashEmbeddingProvider
from subscription_bridge.memory.models import DocumentChunk
from subscription_bridge.memory.vector_store import VectorStore


@pytest.fixture
def store() -> VectorStore:
    return VectorStore()


@pytest.fixture
def sample_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            file_path="hello.py",
            language="python",
            start_line=1,
            end_line=5,
            text="def hello():\n    print('hello')\n",
            chunk_id="chunk1",
            symbols=["hello"],
        ),
        DocumentChunk(
            file_path="world.py",
            language="python",
            start_line=1,
            end_line=5,
            text="def world():\n    print('world')\n",
            chunk_id="chunk2",
            symbols=["world"],
        ),
    ]


def test_empty_store(store: VectorStore) -> None:
    assert store.size == 0


def test_add_chunks(store: VectorStore, sample_chunks: list[DocumentChunk]) -> None:
    embedder = HashEmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in sample_chunks])
    store.add(sample_chunks, embeddings)
    assert store.size == 2


def test_search_returns_top_k(store: VectorStore, sample_chunks: list[DocumentChunk]) -> None:
    embedder = HashEmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in sample_chunks])
    store.add(sample_chunks, embeddings)

    query_emb = embedder.embed_query("hello")
    results = store.search(query_emb, top_k=1)
    assert len(results) == 1
    assert results[0].score >= 0


def test_search_sorted_by_score(store: VectorStore, sample_chunks: list[DocumentChunk]) -> None:
    embedder = HashEmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in sample_chunks])
    store.add(sample_chunks, embeddings)

    query_emb = embedder.embed_query("hello")
    results = store.search(query_emb, top_k=5)
    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_search_empty_returns_empty(store: VectorStore) -> None:
    embedder = HashEmbeddingProvider()
    query_emb = embedder.embed_query("test")
    results = store.search(query_emb, top_k=5)
    assert results == []


def test_save_load(tmp_path: Path, store: VectorStore, sample_chunks: list[DocumentChunk]) -> None:
    embedder = HashEmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in sample_chunks])
    store.add(sample_chunks, embeddings)
    store.save(tmp_path)

    store2 = VectorStore()
    store2.load(tmp_path)
    assert store2.size == 2


def test_mismatched_chunks_embeddings(store: VectorStore, sample_chunks: list[DocumentChunk]) -> None:
    with pytest.raises(ValueError, match="must match"):
        store.add(sample_chunks, [[0.1] * 3])
