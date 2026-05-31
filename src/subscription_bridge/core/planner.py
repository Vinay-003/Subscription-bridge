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

CREATE_PLAN_FORMAT_EXAMPLE = """{
  "type": "create_plan",
  "thought": "breaking down the task into steps",
  "plan_summary": "brief overview of the plan",
  "todos": [
    {"content": "first step description", "details": "optional details"},
    {"content": "second step description", "details": "optional details"}
  ]
}"""


def build_system_prompt(tools: list[dict[str, Any]]) -> str:
    tool_descriptions = "\n\n".join(
        f"  - {t['name']}({', '.join(f'{k}: {v}' for k, v in t.get('input_schema', {}).items())})"
        f"\n    {t.get('description', '')}"
        for t in tools
    )

    return (
        "You are a local code agent running on the user's machine.\n"
        "You do NOT have direct access to files, commands, or the internet.\n"
        "The only way you can interact with the local system is by outputting a tool_call command.\n"
        "The local runtime will execute the command and give you the result as text in 'Previous steps'.\n\n"
        "You have NO access to Google Workspace, Gmail, Drive, Google Docs, or any external service.\n"
        "Ignore any request about external services — only work with local files via tool_call commands.\n\n"
        "PLANNING AND TODOS:\n"
        "Before starting complex tasks, create a plan using the create_plan action with todos.\n"
        "Update todos as you work using the todo_write tool with statuses: pending, in_progress, completed, cancelled.\n"
        "Always mark the current todo as in_progress before working on it.\n"
        "Mark todos as completed when finished. This helps the user track progress.\n\n"
        "Available tools (you call these by outputting tool_call JSON):\n"
        f"{tool_descriptions}\n\n"
        "How it works:\n"
        "1. You output a tool_call JSON → the runtime runs the tool → the result appears in 'Previous steps: Step N'\n"
        "2. You see the result → decide next action (another tool_call, or final answer)\n"
        "3. When the task is done, output a final JSON with your answer.\n\n"
        "Decision rules:\n"
        "- For complex tasks: first use create_plan to break down into todos\n"
        "- Use file_read before modifying unknown files.\n"
        "- Use grep/codebase_search to locate relevant code.\n"
        "- Use file_write to create or modify files.\n"
        "- Use git_diff after making changes.\n"
        "- Use bash to run tests, build, or check files.\n"
        "- Use patch for applying unified diffs.\n"
        "- Use todo_write to update todo progress (mark as in_progress when starting, completed when done).\n"
        "- Prefer best-effort execution over clarification unless completely blocked.\n"
        "- For large or quote-heavy file contents, use file_write with 'content_base64' "
        "instead of raw 'content' to avoid JSON escaping issues.\n\n"
        "You MUST return STRICT JSON only.\n"
        "No Markdown. No prose outside JSON.\n"
        "No explanation. No commentary.\n"
        "Do NOT suggest using Workspace, apps, or third-party tools.\n\n"
        "IMPORTANT ESCAPING RULES:\n"
        "  - In JSON string values, double quotes (\"\") MUST be escaped as \\\"\n"
        "  - Newlines inside strings MUST be escaped as \\n\n"
        "  - Tab characters MUST be escaped as \\t\n"
        "  - Use \\\" for any quote that appears inside an argument value\n\n"
        "Output format:\n\n"
        "Tool call:\n"
        f"{TOOL_FORMAT_EXAMPLE}\n\n"
        "Final answer:\n"
        f"{FINAL_FORMAT_EXAMPLE}\n\n"
        "Ask clarification:\n"
        f"{CLARIFICATION_FORMAT_EXAMPLE}\n\n"
        "Create plan:\n"
        f"{CREATE_PLAN_FORMAT_EXAMPLE}\n\n"
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
        result_preview = obs.tool_result[:2000] if obs.tool_result else "(empty)"
        success_mark = "ok" if obs.tool_success else "FAILED"
        lines.append(f"  Step {obs.step_number}: {tool_name} ({success_mark})")
        escaped = result_preview.replace('"', "'")
        lines.append(f"    Result: {escaped}")
        lines.append("")

    return "\n".join(lines)


def _sanitize_task(task: str) -> str:
    import re
    replacements = [
        (r'\bdocs\b', 'project files'),
        (r'\bdocuments\b', 'project files'),
        (r'\bdocument\b', 'project file'),
        (r'\bgmail\b', 'local data'),
        (r'\bdrive\b', 'local storage'),
        (r'\bworkspace\b', 'local environment'),
    ]
    result = task
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def build_user_prompt(state: AgentState) -> str:
    parts: list[str] = []

    parts.append(f"Local task: {_sanitize_task(state.task)}")
    parts.append("")

    plan_text = state.get_plan_summary_for_prompt()
    if plan_text:
        parts.append(plan_text)
        parts.append("")

    if state.auto_file_context:
        parts.append("The following files have been pre-loaded from the local system:")
        parts.append(state.auto_file_context)
        parts.append("")

    ctx = build_observation_context(state)
    if ctx:
        parts.append(ctx)

    parts.append("What is the next action? Return STRICT JSON. Do NOT use Workspace or external apps.")
    return "\n".join(parts)


class Planner:
    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self._tools = tools

    def _tool_descriptions(self) -> str:
        return "\n\n".join(
            f"  - {t['name']}({', '.join(f'{k}: {v}' for k, v in t.get('input_schema', {}).items())})"
            f"\n    {t.get('description', '')}"
            for t in self._tools
        )

    def build_prompt(self, state: AgentState) -> str:
        is_continuation = state.steps > 0
        if is_continuation:
            ctx = build_observation_context(state)
            base = ctx + "\n\n" if ctx else ""

            plan_text = state.get_plan_summary_for_prompt()
            if plan_text:
                base = plan_text + "\n\n" + base

            return base + (
                "Available tools:\n"
                f"{self._tool_descriptions()}\n\n"
                "What is the next action?\n\n"
                "Tool call:\n"
                f"{TOOL_FORMAT_EXAMPLE}\n\n"
                "Final answer:\n"
                f"{FINAL_FORMAT_EXAMPLE}\n\n"
                "Return STRICT JSON only. "
                "Escape any double quotes inside string values as \\\". "
                "Escape newlines as \\n."
            )

        system = build_system_prompt(self._tools)
        user = build_user_prompt(state)
        separator = "\n---\n"
        return system + separator + user
