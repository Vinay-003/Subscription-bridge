from __future__ import annotations

from subscription_bridge.memory.embeddings import HashEmbeddingProvider
from subscription_bridge.memory.models import DocumentChunk, IndexData
from subscription_bridge.memory.retriever import Retriever


def _make_index(chunks: list[DocumentChunk]) -> IndexData:
    embedder = HashEmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in chunks])
    return IndexData(
        chunks=chunks,
        embeddings=embeddings,
    )


def test_retrieve_returns_results() -> None:
    chunks = [
        DocumentChunk(
            file_path="auth.py", start_line=1, end_line=10,
            text="def authenticate():\n    return True\n",
            chunk_id="c1", symbols=["authenticate"],
        ),
        DocumentChunk(
            file_path="db.py", start_line=1, end_line=10,
            text="def connect():\n    pass\n",
            chunk_id="c2", symbols=["connect"],
        ),
    ]
    index = _make_index(chunks)
    retriever = Retriever()
    results = retriever.retrieve("authenticate", index, top_k=5)
    assert len(results) >= 1


def test_retrieve_top_k_respected() -> None:
    chunks = [
        DocumentChunk(file_path=f"file{i}.py", start_line=1, end_line=5,
                      text=f"function {i}() {{ }}", chunk_id=f"c{i}",
                      symbols=[f"function{i}"])
        for i in range(20)
    ]
    index = _make_index(chunks)
    retriever = Retriever()
    results = retriever.retrieve("function", index, top_k=5)
    assert len(results) <= 5


def test_retrieve_empty_index() -> None:
    index = _make_index([])
    retriever = Retriever()
    results = retriever.retrieve("test", index, top_k=5)
    assert results == []


def test_retrieve_symbol_boost() -> None:
    chunks = [
        DocumentChunk(
            file_path="auth.py", start_line=1, end_line=5,
            text="def authenticate():\n    pass\n",
            chunk_id="c1", symbols=["authenticate"],
        ),
    ]
    index = _make_index(chunks)
    retriever = Retriever()
    results = retriever.retrieve("authenticate", index, top_k=5)
    assert len(results) >= 1
    assert results[0].match_type is not None


def test_retrieve_returned_fields() -> None:
    chunks = [
        DocumentChunk(
            file_path="test.py", start_line=1, end_line=10,
            text="def test_func():\n    return 42\n",
            chunk_id="c1", symbols=["test_func"],
        ),
    ]
    index = _make_index(chunks)
    retriever = Retriever()
    results = retriever.retrieve("test_func", index, top_k=5)
    assert len(results) >= 1
    r = results[0]
    assert r.file_path == "test.py"
    assert r.start_line == 1
    assert r.end_line == 10
