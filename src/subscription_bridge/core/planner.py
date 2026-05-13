from __future__ import annotations

from typing import Any

from subscription_bridge.core.agent_state import AgentState

TOOL_FORMAT_EXAMPLE = """{
  "type": "tool_call",
  "thought": "short operational reason",
  "tool_name": "file_read",
  "arguments": {
    "path": "README.md"
  }
}"""

FINAL_FORMAT_EXAMPLE = """{
  "type": "final",
  "thought": "short operational summary",
  "answer": "final answer for the user"
}"""

CLARIFICATION_FORMAT_EXAMPLE = """{
  "type": "ask_clarification",
  "thought": "why clarification is needed",
  "question": "what do you want to clarify"
}"""


def build_system_prompt(tools: list[dict[str, Any]]) -> str:
    tool_descriptions = "\n\n".join(
        f"  - {t['name']}({', '.join(f'{k}: {v}' for k, v in t.get('input_schema', {}).items())})"
        f"\n    {t.get('description', '')}"
        for t in tools
    )

    return (
        "You are the reasoning engine inside SubscriptionBridge.\n"
        "You must return STRICT JSON only.\n"
        "No Markdown. No prose outside JSON.\n"
        "No explanation. No commentary.\n\n"
        "Available tools:\n"
        f"{tool_descriptions}\n\n"
        "Decision rules:\n"
        "- Use file_read before modifying unknown files.\n"
        "- Use grep/codebase_search to locate relevant code.\n"
        "- Use file_write to create or modify files.\n"
        "- Use git_diff after making changes.\n"
        "- Use bash to run tests, build, or check files.\n"
        "- Use patch for applying unified diffs.\n"
        "- Prefer best-effort execution over clarification unless completely blocked.\n\n"
        "Output format:\n\n"
        "Tool call:\n"
        f"{TOOL_FORMAT_EXAMPLE}\n\n"
        "Final answer:\n"
        f"{FINAL_FORMAT_EXAMPLE}\n\n"
        "Ask clarification:\n"
        f"{CLARIFICATION_FORMAT_EXAMPLE}\n\n"
        "Keep thought short and operational.\n"
        "Do not expose private chain-of-thought.\n"
    )


def build_observation_context(state: AgentState) -> str:
    if not state.observations:
        return ""

    lines: list[str] = ["Previous steps:", ""]
    for obs in state.observations[-5:]:
        action = obs.action
        tool_name = action.get("tool_name", "?")
        result_preview = obs.tool_result[:200] if obs.tool_result else "(empty)"
        success_mark = "ok" if obs.tool_success else "FAILED"
        lines.append(f"  Step {obs.step_number}: {tool_name} ({success_mark})")
        lines.append(f"    Result: {result_preview}")
        lines.append("")

    return "\n".join(lines)


def build_user_prompt(state: AgentState) -> str:
    parts: list[str] = []

    parts.append(f"Task: {state.task}")
    parts.append("")

    ctx = build_observation_context(state)
    if ctx:
        parts.append(ctx)

    parts.append("What is the next action? Return STRICT JSON.")
    return "\n".join(parts)


class Planner:
    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self._tools = tools

    def build_prompt(self, state: AgentState) -> str:
        system = build_system_prompt(self._tools)
        user = build_user_prompt(state)
        separator = "\n---\n"
        return system + separator + user
