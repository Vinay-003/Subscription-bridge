from __future__ import annotations

import pytest

from subscription_bridge.core.errors import ToolNotFoundError
from subscription_bridge.tools.bash import BashTool
from subscription_bridge.tools.executor import ToolExecutor
from subscription_bridge.tools.file_read import FileReadTool
from subscription_bridge.tools.grep import GrepTool
from subscription_bridge.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(FileReadTool())
    r.register(GrepTool())
    r.register(BashTool())
    return r


def test_register_list(registry: ToolRegistry) -> None:
    tools = registry.list_tools()
    names = [t.name for t in tools]
    assert "file_read" in names
    assert "grep" in names
    assert "bash" in names


def test_get_tool(registry: ToolRegistry) -> None:
    tool = registry.get("file_read")
    assert isinstance(tool, FileReadTool)


def test_get_unknown_tool(registry: ToolRegistry) -> None:
    with pytest.raises(ToolNotFoundError, match="unknown_tool"):
        registry.get("unknown_tool")


def test_tool_names(registry: ToolRegistry) -> None:
    names = registry.tool_names
    assert "bash" in names
    assert "file_read" in names


def test_contains(registry: ToolRegistry) -> None:
    assert "file_read" in registry
    assert "nonexistent" not in registry


def test_len(registry: ToolRegistry) -> None:
    assert len(registry) == 3


def test_describe_tools_for_prompt(registry: ToolRegistry) -> None:
    descriptions = registry.describe_tools_for_prompt()
    assert len(descriptions) == 3
    for d in descriptions:
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d


@pytest.mark.asyncio
async def test_executor_runs_tool(registry: ToolRegistry, tmp_path) -> None:
    (tmp_path / "test.txt").write_text("hello executor")
    executor = ToolExecutor(registry, workspace=str(tmp_path))
    result = await executor.execute("file_read", {"path": "test.txt"})
    assert result.success
    assert "hello executor" in result.output


@pytest.mark.asyncio
async def test_executor_unknown_tool(registry: ToolRegistry) -> None:
    executor = ToolExecutor(registry, workspace=".")
    result = await executor.execute("nonexistent_tool", {})
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_executor_catches_exception(registry: ToolRegistry, tmp_path) -> None:
    executor = ToolExecutor(registry, workspace=str(tmp_path))
    result = await executor.execute("file_read", {"path": "nonexistent.txt"})
    assert not result.success
