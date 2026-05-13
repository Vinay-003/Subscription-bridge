from __future__ import annotations

from subscription_bridge.memory.embeddings import (
    HashEmbeddingProvider,
    create_embedding_provider,
)


def test_hash_embedding_dim() -> None:
    provider = HashEmbeddingProvider()
    assert provider.dim == 384


def test_hash_embedding_texts() -> None:
    provider = HashEmbeddingProvider()
    embeddings = provider.embed_texts(["hello world", "test"])
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384
    assert len(embeddings[1]) == 384


def test_hash_embedding_deterministic() -> None:
    provider = HashEmbeddingProvider()
    e1 = provider.embed_texts(["hello world"])
    e2 = provider.embed_texts(["hello world"])
    assert e1 == e2


def test_hash_embedding_different_inputs() -> None:
    provider = HashEmbeddingProvider()
    e1 = provider.embed_texts(["hello"])
    e2 = provider.embed_texts(["world"])
    assert e1 != e2


def test_hash_embedding_normalized() -> None:
    provider = HashEmbeddingProvider()
    emb = provider.embed_texts(["test"])[0]
    norm = sum(v * v for v in emb) ** 0.5
    assert abs(norm - 1.0) < 0.001


def test_hash_embedding_empty_text() -> None:
    provider = HashEmbeddingProvider()
    emb = provider.embed_texts([""])[0]
    assert len(emb) == 384


def test_embed_query() -> None:
    provider = HashEmbeddingProvider()
    emb = provider.embed_query("test query")
    assert len(emb) == 384


def test_create_default_provider() -> None:
    provider = create_embedding_provider("hash")
    assert isinstance(provider, HashEmbeddingProvider)


def test_create_invalid_fallback() -> None:
    provider = create_embedding_provider("invalid_provider")
    assert isinstance(provider, HashEmbeddingProvider)
