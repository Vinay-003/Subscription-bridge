from __future__ import annotations

from typing import Any

from subscription_bridge.core.agent_state import AgentState

_TOOL_CALL_EXAMPLE = (
    '{"type": "tool_call", "tool_name": "<name>", "arguments": {<args>}}'
)
_FINAL_EXAMPLE = '{"type": "final", "thought": "<reason>", "answer": "<text>"}'


def build_system_prompt(tools: list[dict[str, Any]]) -> str:
    tool_lines = []
    for t in tools:
        tname = t["name"]
        tdesc = t.get("description", "")
        tschema = t.get("input_schema", {})
        args = ", ".join(f"{k}: {v}" for k, v in tschema.items())
        tool_lines.append(f"  {tname}({args})\n    {tdesc}")
    tool_desc = "\n".join(tool_lines)

    return (
        "You are an agentic coding assistant running on the user's local machine. "
        "Your job is to take action by calling tools — not to just talk about "
        "what you would do. The user wants the files created, the commands run, "
        "and the result verified.\n\n"
        f"Available tools:\n{tool_desc}\n\n"
        "OUTPUT FORMAT — return STRICT JSON only. No Markdown fences. "
        "No prose outside the JSON. No 'let me explain first'.\n\n"
        "Tool call:\n"
        f"  {_TOOL_CALL_EXAMPLE}\n\n"
        "Final answer (use ONLY when the task is complete and verified):\n"
        f"  {_FINAL_EXAMPLE}\n\n"
        "AGENTIC BEHAVIOUR — read this carefully:\n"
        "  - When the user asks you to create, write, build, or implement "
        "something, you MUST call a tool. NEVER just describe the code in "
        "the 'answer' field.\n"
        "  - When the user asks you to create a file containing code, you "
        "MUST use the file_write tool (or bash with a heredoc) to actually "
        "write the file to disk.\n"
        "  - When the user asks you to run or compile something, you MUST "
        "use the bash tool to run the command.\n"
        "  - After taking an action, look at the result and decide the next "
        "step. If something failed, try a different approach. Don't just "
        "give up and emit a final answer.\n"
        "  - Only emit the 'final' type after the task is actually done "
        "and you have verified the result.\n\n"
        "CRITICAL JSON ESCAPING (errors here break file writes):\n"
        "  - Inside any JSON string value, double quotes MUST be \\\"\n"
        "  - Newlines inside strings MUST be the two characters backslash+n (\\n), "
        "NEVER a raw newline character\n"
        "  - Backslashes inside strings MUST be \\\\ (two chars)\n"
        "  - Tabs MUST be \\t\n\n"
        "WRITING CODE FILES — use bash with a single-quoted heredoc (most reliable):\n"
        '  bash command: cat > file.c <<\'CFILE\'\n'
        "  <full file content, no escaping needed>\n"
        "  CFILE\n"
        "The single quotes around the delimiter (<<\'CFILE\') disable shell "
        "expansion, so backslashes and quotes inside the heredoc body are "
        "written verbatim. This is the safest way to write any file containing "
        "code with backslashes or double quotes.\n\n"
        "ALTERNATIVE: use file_write with a properly-escaped 'content' field. "
        "For multi-line C/Python/JS code, the bash heredoc is strongly preferred "
        "because you don't have to escape anything.\n\n"
        "NEVER use content_base64 — you cannot generate valid base64 reliably.\n\n"
        "Do NOT call tools for greetings, small talk, or pure questions — for "
        "those, just emit a final JSON with the answer text."
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

    parts.append("Respond with text, or use tools if needed.")
    return "\n".join(parts)


class Planner:
    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self._tools = tools

    def build_prompt(self, state: AgentState) -> str:
        is_continuation = state.steps > 0
        if is_continuation:
            ctx = build_observation_context(state)
            base = ctx + "\n\n" if ctx else ""

            plan_text = state.get_plan_summary_for_prompt()
            if plan_text:
                base = plan_text + "\n\n" + base

            return base + (
                "Continue. Use a tool if needed, or respond with text."
            )

        system = build_system_prompt(self._tools)
        user = build_user_prompt(state)
        separator = "\n---\n"
        return system + separator + user
