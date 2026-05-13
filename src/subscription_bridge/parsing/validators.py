from __future__ import annotations

from typing import Any

from subscription_bridge.parsing.schemas import AgentAction


def validate_tool_name(tool_name: str) -> str:
    valid_tools = {
        "file_read",
        "file_write",
        "grep",
        "bash",
        "git_diff",
        "patch",
        "codebase_search",
    }
    if tool_name in valid_tools:
        return tool_name
    msg = (
        f"Unknown tool {tool_name!r}. Valid tools: {', '.join(sorted(valid_tools))}"
    )
    raise ValueError(msg)


def validate_action_schema(data: dict[str, Any]) -> AgentAction:
    return AgentAction.from_dict(data)
