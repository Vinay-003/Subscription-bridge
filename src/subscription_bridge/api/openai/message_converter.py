from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import socket
import tempfile
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


def convert_messages(
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    require_json_tools: bool = False,
    full_history: bool = False,
) -> tuple[str, str]:
    """Convert OpenCode messages into a browser-LLM prompt + system prompt.

    Design: pure transparent proxy. Pass OpenCode's system prompts and
    conversation through as-is. Only append a minimal tool-format instruction
    when tools are present. Do not rewrite, compact, or reformat the content.
    """
    system_parts: list[str] = []
    conversation: list[str] = []

    for msg in messages:
        if getattr(msg, "role", None) == "system":
            raw = extract_text(msg.content) if msg.content else ""
            if raw.strip():
                system_parts.append(raw.strip())

    for msg in messages:
        role = getattr(msg, "role", None)
        if role == "system":
            continue
        text = extract_text(msg.content) if msg.content else ""

        if role == "user":
            if text.strip():
                conversation.append(f"User: {text}")
        elif role == "assistant":
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls or []:
                    name = tc.get("function", {}).get("name", "?") if isinstance(tc, dict) else "?"
                    args = tc.get("function", {}).get("arguments", "{}") if isinstance(tc, dict) else "{}"
                    conversation.append(f"Assistant called tool {name} with arguments: {args}")
            if text.strip():
                conversation.append(f"Assistant: {text}")
        elif role == "tool":
            tool_id = getattr(msg, "tool_call_id", "") or ""
            label = f"Tool result ({tool_id})" if tool_id else "Tool result"
            conversation.append(f"{label}: {text}")

    if tools and require_json_tools:
        system_parts.append(_tool_instruction(tools, tool_choice))

    system_prompt = "\n\n".join(system_parts) if system_parts else ""
    prompt = "\n".join(conversation) if conversation else ""
    return prompt, system_prompt


SYSTEM_CONTEXT_TAG = "context_overview"
SYSTEM_CONTRACT_TAG = "operating_instructions"
COMPACT_SYSTEM_BUDGET_TOKENS = 2000

_COMPACT_HEADER = (
    "Earlier conversation turns were compacted by the client and are summarized "
    "below. Continue the session under these operating rules:\n\n"
)

# Marker, keep_marker: first marker that yields two real sections wins.
# ``keep_marker=True`` leaves the closing tag in the context half.
_PART2_MARKERS: tuple[tuple[str, bool], ...] = (
    ("</available_skills>", True),
    ("</skills>", True),
    ("\nYou have access to tools. Available tools:", False),
    ("\n## Available Commands", False),
    ("\n# Tools", False),
    ("\n## Tools", False),
    ("\n## Tool Usage", False),
)

_COMPACT_SOURCE_MARKERS = (
    "# Operational Guidelines",
    "## Tone and Style",
    "# Final Reminder",
)

_MIN_SECTION_CHARS = 200
_TOOL_INSTRUCTION_MARKER = "\nYou have access to tools. Available tools:"


def split_system_prompt(text: str) -> tuple[str, str]:
    """Split a system prompt into background context and operating contract.

    Part 1 carries the identity/env/skills material ("who and where I am"),
    part 2 carries the tools and rules ("what I must do"). Prompts without a
    recognisable boundary fall back to a paragraph break near the midpoint.
    Returns ``(text, "")`` when no meaningful split exists.
    """
    stripped = text.strip()
    if not stripped:
        return "", ""
    if len(stripped) < _MIN_SECTION_CHARS * 2:
        return stripped, ""
    for marker, keep_marker in _PART2_MARKERS:
        idx = stripped.find(marker)
        if idx == -1:
            continue
        cut = idx + len(marker) if keep_marker else idx
        part1, part2 = stripped[:cut].strip(), stripped[cut:].strip()
        if len(part1) >= _MIN_SECTION_CHARS and len(part2) >= _MIN_SECTION_CHARS:
            return part1, part2
    return _midpoint_split(stripped)


def render_system_prompt(system_prompt: str) -> str:
    """Wrap a system prompt in two labelled blocks for the first browser turn.

    Delimited sections give the browser model a clear boundary between
    background context and the operating contract instead of one undifferentiated
    wall of text. Prompts that do not split are forwarded unchanged.
    """
    part1, part2 = split_system_prompt(system_prompt)
    if not part1 or not part2:
        return system_prompt
    return (
        f"<{SYSTEM_CONTEXT_TAG}>\n{part1}\n</{SYSTEM_CONTEXT_TAG}>\n\n"
        f"<{SYSTEM_CONTRACT_TAG}>\n{part2}\n</{SYSTEM_CONTRACT_TAG}>"
    )


def compact_system_prompt(system_prompt: str) -> str:
    """Build the short reminder re-sent after the client compacts history.

    Compaction keeps the system message in the transcript, so re-sending it in
    full would re-add the entire initial prompt to an already-summarized context.
    Only a bounded slice of the operating rules is forwarded instead; the tool
    contract is always preserved because tool calling breaks without it.
    """
    text = system_prompt.strip()
    if not text:
        return ""
    head, tool_contract = _split_tool_instruction(text)
    source = ""
    for marker in _COMPACT_SOURCE_MARKERS:
        idx = head.find(marker)
        if idx != -1:
            source = head[idx:]
            break
    if not source:
        _, part2 = split_system_prompt(head)
        source = part2 or head
    compacted = _truncate_chars(source, COMPACT_SYSTEM_BUDGET_TOKENS * 4)
    if tool_contract:
        return f"{_COMPACT_HEADER}{compacted}\n\n{tool_contract}"
    return _COMPACT_HEADER + compacted


_DELTA_REFERENCE_HEADER = "[Reminder - still in effect from the first message of this conversation]"

_DELTA_REFERENCE_SYSTEM = (
    "The system prompt sent in the first message "
    f"(<{SYSTEM_CONTEXT_TAG}> and <{SYSTEM_CONTRACT_TAG}>) applies to this entire "
    "session: follow it exactly, as if it had just been sent."
)

_DELTA_REFERENCE_TOOLS = (
    "You also have tool access: the tool definitions and the JSON tool-call "
    "contract from the first message remain in force. For ANY request that needs "
    "local information - file contents, directory listings, search, or running "
    "commands - respond with a tool call in exactly this format and nothing else:\n"
    '{"tool_calls": [{"function": {"name": "<tool name from the first message>", '
    '"arguments": {"<arg>": "<value>"}}}]}\n'
    "Never tell the user you have no access to local files or a terminal; you "
    "operate those tools yourself."
)


def delta_reference_note(has_tools: bool) -> str:
    """Reference block appended to every browser message after the first turn.

    The system prompt and tool contract are delivered once, inside message 1.
    Later turns carry only the conversation delta, and the browser model drifts
    back to a generic assistant persona (e.g. claiming it cannot touch the
    filesystem). Re-pointing at message 1 on every follow-up keeps the agent
    contract binding for the whole session.
    """
    paragraphs = [_DELTA_REFERENCE_HEADER, _DELTA_REFERENCE_SYSTEM]
    if has_tools:
        paragraphs.append(_DELTA_REFERENCE_TOOLS)
    return "\n\n" + "\n\n".join(paragraphs)


# The template, rules, and structure mirror OpenCode's own session compaction
# prompt (packages/core/src/session/compaction.ts) so a handoff summary reads
# the same to the browser model as OpenCode's in-client summaries do.
_SWITCH_COMPACTION_TEMPLATE = """You MUST use this format for your response (you may omit sections
that aren't applicable). Do not include the <template> tags in your response.
<template>
## Objective
- [one or two brief sentences describing what the user is trying to accomplish]

## Requirements
- [constraints, preferences, requirements, and scope boundaries stated by the user, or "(none)"]

## Decisions
- [decisions already made and why, or "(none)"]

## Work State
Break the objective into smaller goals and report which are completed, which are being worked on, and which are blocked.
### Completed
- [goals that have been completed; otherwise "(none)"]

### Active
- [goals currently being worked on; otherwise "(none)"]

### Blocked
- [anything blocking progress, and why; otherwise "(none)"]

## Next Move
1. [ordered list of next actions, or "(none)"]

## Relevant Files
List the files and directories, other than the current working directory, that another agent
would need to open to continue this work. Include at most 15, most important first. Do not list
every file that was read or changed. Include paths outside the current working directory when
relevant. If none, write "(none)".
- `[file or directory path]`: [brief reason it matters]

## Important Context
- [facts the next agent cannot continue without and cannot easily find on its own; or "(none)"]
</template>"""

_SWITCH_COMPACTION_RULES = """Rules:
- Keep each section concise. Use terse, single-line bullets, not prose paragraphs or nested lists.
- Prefer short references over detailed restatement. It is fine to leave out information the
  next agent can recover from the code or the files listed above.
- Preserve exact file paths, symbols, commands, error strings, URLs, and identifiers.
- Carry forward only user questions or requests that remain unanswered or require further action.
  Do not repeat ones that newer history has answered or resolved. Preserve exact wording when
  carrying one forward.
- Preserve consequential workflow state, including whether changes are uncommitted, committed,
  pushed, under review, or merged.
- Do not mention the summary process or that context was compacted."""

_SWITCH_COMPACTION_EXCLUSION = (
    "Summarize only what the user and the assistant said and did. Leave out "
    "instructions and setup the assistant was given rather than told by the "
    "user: repository conventions, instruction files such as AGENTS.md, "
    "environment details like the session ID, and every rule, policy, or "
    "instruction that arrived in the first message of this conversation (its "
    "system prompt). The next agent receives current versions of all of these "
    "separately in its own first message, so do not mention, restate, or carry "
    "forward any of them."
)


def build_switch_compaction_prompt() -> str:
    """Prompt asking the outgoing browser chat to summarize the session.

    Used when the client switches models/providers mid-session: the old
    provider still holds the full conversation, so it produces the handoff
    summary that the new provider receives as its first post-system message.
    Mirrors OpenCode's compaction instructions (Objective/Requirements/
    Decisions/Work State/Next Move/Relevant Files/Important Context) plus an
    explicit ban on carrying first-message system-prompt rules forward.
    """
    return "\n\n".join(
        [
            "You MUST summarize the conversation above into a structured summary "
            "that will be given to another agent to resume the work.",
            _SWITCH_COMPACTION_EXCLUSION,
            _SWITCH_COMPACTION_TEMPLATE,
            _SWITCH_COMPACTION_RULES,
            "Do not continue the task or call tools.",
            "Return only the structured summary in the requested format. Do not "
            "include a preamble, explanation, or other commentary.",
        ]
    )


LOCAL_HISTORY_EXCERPT_CHARS = 12000


def local_history_excerpt(
    messages: list[Any], limit_chars: int = LOCAL_HISTORY_EXCERPT_CHARS
) -> str:
    """Render a bounded transcript used when the old provider cannot summarize.

    Fallback for a provider-switch handoff where the outgoing browser chat is
    unreachable or refuses to compact: keep only the most recent part of the
    covered history instead of re-sending everything to the new provider.
    """
    parts: list[str] = []
    for msg in messages:
        role = str(getattr(msg, "role", "") or "")
        if role == "system":
            continue
        content = getattr(msg, "content", None)
        text = extract_text(content) if isinstance(content, (str, list)) else ""
        if not text.strip():
            continue
        label = {"user": "User", "assistant": "Assistant", "tool": "Tool result"}.get(
            role, role or "Message"
        )
        parts.append(f"{label}: {text}")
    if not parts:
        return ""
    transcript = "\n".join(parts)
    if len(transcript) <= limit_chars:
        return f"Previous conversation:\n\n{transcript}"
    tail = transcript[-limit_chars:]
    cut = tail.find("\n")
    if 0 <= cut < 400:
        tail = tail[cut + 1 :]
    return f"Previous conversation (truncated to the most recent part):\n\n{tail}"


def _midpoint_split(text: str) -> tuple[str, str]:
    midpoint = len(text) // 2
    cut = text.rfind("\n\n", 0, midpoint)
    if cut == -1 or cut < len(text) * 0.15:
        cut = text.find("\n\n", midpoint)
    if cut == -1:
        return text, ""
    part1, part2 = text[:cut].strip(), text[cut:].strip()
    if len(part1) < _MIN_SECTION_CHARS or len(part2) < _MIN_SECTION_CHARS:
        return text, ""
    return part1, part2


def _truncate_chars(text: str, limit: int) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    cut = stripped.rfind("\n", 0, limit)
    if cut < limit // 2:
        cut = limit
    return stripped[:cut].rstrip()


def _split_tool_instruction(text: str) -> tuple[str, str]:
    """Split the appended tool contract off the tail of a system prompt."""
    idx = text.rfind(_TOOL_INSTRUCTION_MARKER)
    if idx != -1:
        return text[:idx].strip(), text[idx:].strip()
    if text.startswith("You have access to tools. Available tools:"):
        return "", text.strip()
    return text, ""


def _tool_instruction(
    tools: list[dict[str, Any]],
    tool_choice: str | dict[str, Any] | None,
) -> str:
    tools_desc_lines = []
    for tool in tools:
        fn = tool.get("function", tool) if isinstance(tool, dict) else {}
        if not isinstance(fn, dict):
            continue
        fname = fn.get("name", "?")
        fdesc = fn.get("description", "")
        fparams = fn.get("parameters", {})
        schema = json.dumps(fparams, ensure_ascii=False, separators=(",", ":"))
        tools_desc_lines.append(f"- {fname}: {fdesc}\n  Parameters schema: {schema}")
    tools_desc = "\n".join(tools_desc_lines)

    instruction = f"""You have access to tools. Available tools:
{tools_desc}

When you need to use a tool, respond with ONLY a JSON object in this exact format and nothing else:

{{"tool_calls": [{{"function": {{"name": "tool_name", "arguments": {{"arg1": "value1", "arg2": "value2"}}}}}}]}}

Rules:
- The "arguments" object must match the Parameters schema for that tool.
- To call multiple tools, include multiple entries in the "tool_calls" array.
- Escape any double quotes inside string argument values.
- If you do not need any tool, respond with normal text (not JSON).
- Do not wrap the JSON in Markdown code fences.
- Do not add any commentary before or after the JSON."""

    if tool_choice == "required":
        instruction += "\n\nIMPORTANT: A tool call is REQUIRED. You MUST respond with a tool_calls JSON object."
    elif isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        forced = tool_choice.get("function", {})
        forced_name = forced.get("name") if isinstance(forced, dict) else None
        if forced_name:
            instruction += f"\n\nIMPORTANT: You MUST call only the tool named '{forced_name}'."

    return instruction


def extract_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(str(part.get("text", "")))
    return "\n".join(texts)


def extract_images_from_content(content: str | list[dict[str, Any]]) -> list[str]:
    if isinstance(content, str):
        return []
    paths: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            url = part.get("image_url", {})
            if isinstance(url, dict):
                url = url.get("url", "")
            if not url:
                continue
            path = save_image(url)
            if path:
                paths.append(path)
    return paths


_MAX_REMOTE_IMAGE_BYTES = 20 * 1024 * 1024


def _is_public_http_url(url: str) -> bool:
    """Reject local/private targets so arbitrary image URLs cannot reach intranet services."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
            return address.is_global
        except ValueError:
            pass
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError, socket.gaierror):
        return False


def save_image(url: str) -> str | None:
    try:
        if url.startswith("data:"):
            match = re.match(r"data:image/(\w+);base64,(.+)", url)
            if not match:
                return None
            ext = match.group(1).lower()
            data = base64.b64decode(match.group(2), validate=True)
            if len(data) > _MAX_REMOTE_IMAGE_BYTES:
                return None
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=f".{ext}", delete=False, prefix="bridge_img_",
            ) as f:
                f.write(data)
                return f.name

        target = url
        response = None
        for _ in range(4):
            if not _is_public_http_url(target):
                return None
            response = httpx.get(target, timeout=30, follow_redirects=False)
            if response.status_code not in (301, 302, 303, 307, 308):
                break
            location = response.headers.get("location")
            if not location:
                return None
            target = urljoin(target, location)
        if response is None or response.status_code in (301, 302, 303, 307, 308):
            return None
        response.raise_for_status()
        if len(response.content) > _MAX_REMOTE_IMAGE_BYTES:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "gif" in content_type:
            ext = "gif"
        elif "webp" in content_type:
            ext = "webp"
        elif "png" in content_type:
            ext = "png"
        else:
            return None
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=f".{ext}", delete=False, prefix="bridge_img_",
        ) as f:
            f.write(response.content)
            return f.name
    except Exception:
        return None


def cleanup_temp_files(paths: list[str]) -> None:
    for path in paths:
        try:
            os.unlink(path)
        except Exception:
            pass
