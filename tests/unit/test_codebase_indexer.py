from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.memory.codebase_indexer import CodebaseIndexer


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "src" / "utils.py").write_text("import os\n\ndef helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Project\n\nA sample project.\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("ignored")
    return tmp_path


@pytest.mark.asyncio
async def test_index_creates_data(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    data = indexer.index()
    assert data.metadata.file_count >= 2
    assert data.metadata.chunk_count >= 2


@pytest.mark.asyncio
async def test_index_skips_git(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    data = indexer.index()
    for chunk in data.chunks:
        assert ".git" not in chunk.file_path


@pytest.mark.asyncio
async def test_index_skips_node_modules(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    data = indexer.index()
    for chunk in data.chunks:
        assert "node_modules" not in chunk.file_path


@pytest.mark.asyncio
async def test_index_writes_metadata(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    indexer.index()
    meta_file = indexer.index_dir / "metadata.json"
    assert meta_file.exists()
    assert "workspace_root" in meta_file.read_text()


@pytest.mark.asyncio
async def test_index_saves_chunks(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    indexer.index()
    chunks_file = indexer.index_dir / "chunks.json"
    assert chunks_file.exists()


@pytest.mark.asyncio
async def test_index_saves_embeddings(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    indexer.index()
    emb_file = indexer.index_dir / "embeddings.npy"
    assert emb_file.exists()


@pytest.mark.asyncio
async def test_load_existing_index(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    indexer.index()

    indexer2 = CodebaseIndexer(workspace=str(fixture_repo))
    data = indexer2.load_existing()
    assert data is not None
    assert data.metadata.file_count >= 2


@pytest.mark.asyncio
async def test_load_nonexistent_index(tmp_path: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(tmp_path))
    data = indexer.load_existing()
    assert data is None


@pytest.mark.asyncio
async def test_index_summary(fixture_repo: Path) -> None:
    indexer = CodebaseIndexer(workspace=str(fixture_repo))
    data = indexer.index()
    summary = data.summary()
    assert "workspace_root" in summary
    assert "file_count" in summary
    assert "chunk_count" in summary
