from __future__ import annotations

import os
from pathlib import Path

import pytest

from subscription_bridge.tools.bash import BashTool
from subscription_bridge.tools.executor import ToolExecutor
from subscription_bridge.tools.file_read import FileReadTool
from subscription_bridge.tools.file_write import FileWriteTool
from subscription_bridge.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(FileReadTool())
    r.register(FileWriteTool())
    r.register(BashTool())
    return r


@pytest.mark.asyncio
async def test_executor_uses_configured_workspace(registry: ToolRegistry, tmp_path: Path) -> None:
    ws = str(tmp_path)
    executor = ToolExecutor(registry, workspace=ws)
    assert executor._workspace == os.path.abspath(ws)


@pytest.mark.asyncio
async def test_executor_normalizes_workspace(registry: ToolRegistry, tmp_path: Path) -> None:
    executor = ToolExecutor(registry, workspace=str(tmp_path))
    assert executor._workspace == os.path.abspath(str(tmp_path))


@pytest.mark.asyncio
async def test_tool_operates_in_configured_workspace(registry: ToolRegistry, tmp_path: Path) -> None:
    ws = str(tmp_path)
    executor = ToolExecutor(registry, workspace=ws)

    result = await executor.execute("file_write", {"path": "hello.txt", "content": "world"})
    assert result.success
    assert (Path(ws) / "hello.txt").read_text() == "world"


@pytest.mark.asyncio
async def test_tool_does_not_use_models_workspace(registry: ToolRegistry, tmp_path: Path) -> None:
    ws = str(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    executor = ToolExecutor(registry, workspace=str(ws))

    result = await executor.execute("file_write", {
        "path": "test.txt", "content": "data", "workspace": str(other),
    })
    assert result.success
    assert (Path(ws) / "test.txt").read_text() == "data"
    assert not (other / "test.txt").exists()


@pytest.mark.asyncio
async def test_bash_runs_in_configured_workspace(registry: ToolRegistry, tmp_path: Path) -> None:
    ws = str(tmp_path)
    executor = ToolExecutor(registry, workspace=ws)

    result = await executor.execute("bash", {"command": "pwd", "timeout": 5})
    assert result.success
    assert ws in result.output


@pytest.mark.asyncio
async def test_executor_default_workspace_is_cwd(registry: ToolRegistry) -> None:
    executor = ToolExecutor(registry)
    assert executor._workspace == os.path.abspath(".")


@pytest.mark.asyncio
async def test_executor_path_traversal_still_blocked(registry: ToolRegistry, tmp_path: Path) -> None:
    ws = str(tmp_path)
    executor = ToolExecutor(registry, workspace=ws)

    result = await executor.execute("file_write", {"path": "../outside.txt", "content": "x"})
    assert not result.success
    assert "Path traversal" in result.error
