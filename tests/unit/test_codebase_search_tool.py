from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.tools.codebase_search import CodebaseSearchTool


@pytest.mark.asyncio
async def test_no_index_returns_helpful_message(tmp_path: Path) -> None:
    tool = CodebaseSearchTool()
    result = await tool.run({"query": "test", "workspace": str(tmp_path)})
    assert result.success
    assert "No codebase index found" in result.output
    assert "bridge codebase index" in result.output


@pytest.mark.asyncio
async def test_empty_query(tmp_path: Path) -> None:
    tool = CodebaseSearchTool()
    result = await tool.run({"query": "", "workspace": str(tmp_path)})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_with_index_returns_results(tmp_path: Path) -> None:
    from subscription_bridge.memory.codebase_indexer import CodebaseIndexer

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def authenticate():\n    return True\n")
    (tmp_path / "README.md").write_text("# Project")

    indexer = CodebaseIndexer(workspace=str(tmp_path))
    indexer.index()

    tool = CodebaseSearchTool()
    result = await tool.run({"query": "authenticate", "workspace": str(tmp_path)})
    assert result.success
    assert "authenticate" in result.output or "Found" in result.output


@pytest.mark.asyncio
async def test_with_index_no_matches(tmp_path: Path) -> None:
    from subscription_bridge.memory.codebase_indexer import CodebaseIndexer

    (tmp_path / "main.py").write_text("x = 1\n")

    indexer = CodebaseIndexer(workspace=str(tmp_path))
    indexer.index()

    tool = CodebaseSearchTool()
    result = await tool.run({"query": "zzz_nonexistent", "workspace": str(tmp_path)})
    assert result.success
    assert result.metadata.get("indexed") is True
