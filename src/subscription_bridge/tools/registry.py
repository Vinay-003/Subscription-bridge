from __future__ import annotations

from typing import Any

from subscription_bridge.core.errors import ToolNotFoundError
from subscription_bridge.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def describe_tools_for_prompt(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for tool in self._tools.values():
            result.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": dict(tool.input_schema),
            })
        return result

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
