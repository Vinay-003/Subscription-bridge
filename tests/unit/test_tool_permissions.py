from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.tools.base import Tool, ToolResult
from subscription_bridge.tools.executor import ToolExecutor
from subscription_bridge.tools.file_read import FileReadTool
from subscription_bridge.tools.file_write import FileWriteTool
from subscription_bridge.tools.registry import ToolRegistry


class TimeoutEchoTool(Tool):
    name = "bash"

    async def run(self, arguments: dict) -> ToolResult:
        return ToolResult(name=self.name, success=True, metadata={"timeout": arguments.get("timeout")})


def _registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


@pytest.mark.asyncio
async def test_executor_rejects_disabled_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "subscription_bridge.tools.executor.load_tool_permissions",
        lambda: {"file_read": {"enabled": False}},
    )
    executor = ToolExecutor(_registry(FileReadTool()), workspace=str(tmp_path))

    result = await executor.execute("file_read", {"path": "hello.txt"})


    assert not result.success
    assert "disabled" in (result.error or "")


@pytest.mark.asyncio
async def test_executor_rejects_denied_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "subscription_bridge.tools.executor.load_tool_permissions",
        lambda: {"file_write": {"enabled": True, "allow_paths": ["."], "deny_paths": [".env*"]}},
    )
    executor = ToolExecutor(_registry(FileWriteTool()), workspace=str(tmp_path))

    result = await executor.execute("file_write", {"path": ".env", "content": "SECRET=value"})

    assert not result.success
    assert "denied" in (result.error or "")
    assert not (tmp_path / ".env").exists()


@pytest.mark.asyncio
async def test_executor_rejects_path_traversal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "subscription_bridge.tools.executor.load_tool_permissions",
        lambda: {"file_read": {"enabled": True, "allow_paths": ["."]}},
    )
    executor = ToolExecutor(_registry(FileReadTool()), workspace=str(tmp_path))

    result = await executor.execute("file_read", {"path": "../outside.txt"})

    assert not result.success
    assert "traversal" in (result.error or "")


@pytest.mark.asyncio
async def test_executor_clamps_configured_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "subscription_bridge.tools.executor.load_tool_permissions",
        lambda: {"bash": {"enabled": True, "timeout_seconds": 5}},
    )
    executor = ToolExecutor(_registry(TimeoutEchoTool()), workspace=str(tmp_path))

    result = await executor.execute("bash", {"command": "sleep 60", "timeout": 60})

    assert result.success
    assert result.metadata["timeout"] == 5
