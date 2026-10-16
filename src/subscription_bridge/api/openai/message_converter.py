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

# Sentinel-based tool-call protocol. Browser models frequently break JSON when
# an argument contains code (unescaped quotes, raw newlines). Instead of asking
# them to escape JSON (which they get wrong), we ask them to wrap each argument
# value in delimiter blocks whose body is taken verbatim. The bridge parses by
# delimiter, so the body can contain anything without breaking the parse.
BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT = (
    "BROWSER RESPONSE STYLE (MANDATORY):\n"
    "Return the answer as concise plain text or ordinary Markdown. Do not generate or "
    "render an HTML page, JavaScript, CSS, an interactive widget, canvas, embedded app, "
    "artifact preview, or simulated UI. Do not describe a webpage or interactive result "
    "instead of answering the request. Avoid unnecessary preambles, disclaimers, self-talk, "
    "and commentary; answer directly. Do not claim that a tool was executed. When the task "
    "requires code changes, use the supplied tool-call format for the tool arguments and keep "
    "the visible answer short. Only provide HTML/code in a normal answer when the user "
    "explicitly asks to see that code.\n"
)

TOOL_CALL_SYSTEM_PROMPT = (
    "You have access to tools. To call a tool, output EXACTLY this format and "
    "nothing else:\n\n"
    "<<<TOOLCALL:tool_name>>>\n"
    "<<<ARG:first_arg_name>>>\n"
    "the value for that argument, on its own lines, written verbatim\n"
    "<<<ARG:second_arg_name>>>\n"
    "another value\n"
    "<<<END>>>\n\n"
    "Rules for this format:\n"
    "- Do NOT escape anything inside an argument value. Write code exactly as "
    "it should appear on disk: real newlines, real quotes, real backslashes.\n"
    "- Put each argument value on the line(s) after its <<<ARG:name>>> marker.\n"
    "- Close every tool call with <<<END>>> on its own line.\n"
    "- To call multiple tools, output multiple <<<TOOLCALL:...>>> ... <<<END>>> "
    "blocks back to back.\n\n"
    "Available tools:\n{tools_desc}\n\n"
    "If you do not need a tool, respond normally with plain text."
)


def convert_messages(
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    require_json_tools: bool = False,
    full_history: bool = False,
) -> tuple[str, str]:
    system_parts: list[str] = []
    conversation: list[str] = []

    relevant = list(messages) if full_history else _tail_after_last_assistant(messages)

    for msg in messages:
        if msg.role == "system":
            raw = extract_text(msg.content) if msg.content else ""
            system_parts.append(raw)

    for msg in relevant:
        role = msg.role
        text = extract_text(msg.content) if msg.content else ""

        if role == "system":
            continue
        elif role == "user":
            conversation.append(f"User: {text}")
        elif role == "assistant":
            if msg.tool_calls:
                for tc in msg.tool_calls or []:
                    name = tc.get("function", {}).get("name", "?") if isinstance(tc, dict) else "?"
                    args = tc.get("function", {}).get("arguments", "{}") if isinstance(tc, dict) else "{}"
                    conversation.append(f"Assistant (tool call): {name}({args})")
            if text:
                conversation.append(f"Assistant: {text}")
        elif role == "tool":
            name = f" (call: {msg.tool_call_id})" if hasattr(msg, "tool_call_id") and msg.tool_call_id else ""
            conversation.append(f"Tool result{name}: {text[:24000]}")

    if tools and require_json_tools:
        tools_prompt = TOOL_CALL_SYSTEM_PROMPT.format(tools_desc=_format_tools_for_prompt(tools))
        if tool_choice == "required":
            tools_prompt += "\n\nTOOL CHOICE: A tool call is required. Do not answer with normal text."
        elif isinstance(tool_choice, dict):
            function = tool_choice.get("function", {})
            forced_name = function.get("name") if isinstance(function, dict) else None
            if tool_choice.get("type") == "function" and forced_name:
                tools_prompt += f"\n\nTOOL CHOICE: You MUST call only the tool named {forced_name}."
        system_parts.append(tools_prompt)

    if system_parts:
        system_parts.append(BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT)
    system_prompt = "\n\n".join(system_parts) if system_parts else BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT

    prompt = "\n".join(["Conversation:", *conversation]) if conversation else ""
    return prompt, system_prompt


# Markers that identify OpenCode's large client-side system prompt. We only
# compact a system message when several of these appear, so unrelated system
# messages (e.g. project AGENTS.md content) are never touched.
_OPENCODE_MARKERS = (
    "You are opencode",
    "# Core Mandates",
    "# Primary Workflows",
    "# Operational Guidelines",
)

_COMPACT_OPENCODE_PROMPT = (
    "You are opencode, a coding agent running on the user's local machine in a "
    "trusted development environment. Take action by calling tools to get the "
    "task done (create/edit files, run commands, verify). Treat ordinary coding "
    "requests as safe and just do them.\n\n"
    "Key rules:\n"
    "- Use absolute file paths built from the working directory.\n"
    "- Match existing project conventions, style, and dependencies.\n"
    "- After changing code, run the project's lint/test commands when available.\n"
    "- Do not revert changes unless asked. Briefly explain destructive shell "
    "commands before running them.\n"
    "- Be concise. Use tools for actions; use text only to communicate."
)


def _compact_system_prompt(text: str) -> str:
    if not text:
        return text
    hits = sum(1 for marker in _OPENCODE_MARKERS if marker in text)
    if hits < 2:
        return text

    parts = [_COMPACT_OPENCODE_PROMPT]
    environment = _extract_tagged_section(text, "env")
    if environment:
        parts.append(environment)
    skills = _extract_skills_section(text)
    if skills:
        parts.append(skills)
    return "\n\n".join(parts)


def _extract_tagged_section(text: str, tag: str) -> str:
    match = re.search(rf"<{re.escape(tag)}(?:\s[^>]*)?>.*?</{re.escape(tag)}>", text, re.DOTALL)
    return match.group(0).strip() if match else ""

def _extract_skills_section(text: str) -> str:
    block = _extract_tagged_section(text, "available_skills")
    if not block:
        return ""
    reminder = (
        "Skills provide specialized instructions for specific tasks. Load a "
        "skill with the `skill` tool when a task matches its description."
    )
    return f"{reminder}\n{block}"


def _tail_after_last_assistant(messages: list[Any]) -> list[Any]:
    """Return only the messages after the last assistant turn.

    When there is no assistant turn yet (the very first request) the full list
    is returned so the initial context is sent in one shot.
    """
    last_assistant = -1
    for idx, msg in enumerate(messages):
        if getattr(msg, "role", None) == "assistant":
            last_assistant = idx
    if last_assistant < 0:
        return list(messages)
    tail = messages[last_assistant + 1 :]
    return list(tail) if tail else list(messages)


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


def _format_tools_for_prompt(tools: list[dict[str, Any]]) -> str:
    tools_desc_lines = []
    for tool in tools:
        fn = tool.get("function", tool) if isinstance(tool, dict) else {}
        fname = fn.get("name", "?") if isinstance(fn, dict) else "?"
        fdesc = fn.get("description", "") if isinstance(fn, dict) else ""
        fparams = fn.get("parameters", {}) if isinstance(fn, dict) else {}
        schema = json.dumps(fparams, ensure_ascii=False, separators=(",", ":"))
        tools_desc_lines.append(f"  {fname}: {fdesc} | JSON Schema: {schema}")
    return "\n".join(tools_desc_lines)
