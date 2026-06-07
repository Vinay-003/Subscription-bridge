from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from typing import Any

import httpx

TOOL_CALL_SYSTEM_PROMPT = (
    'You have access to tools. When you need to use a tool, '
    'respond with a JSON object: {{"tool_calls": [{{"id": "call_1", '
    '"type": "function", "function": {{"name": "tool_name", '
    '"arguments": {{"arg1": "value1"}}}}}}]}}\n\n'
    "Available tools:\n{tools_desc}\n\n"
    "If you do not need a tool, respond normally with plain text."
)


def convert_messages(
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    require_json_tools: bool = False,
) -> tuple[str, str]:
    del tool_choice

    system_parts: list[str] = []
    conversation: list[str] = []

    for msg in messages:
        role = msg.role
        content = msg.content
        text = extract_text(content) if content else ""

        if role == "system":
            system_parts.append(text)
        elif role == "user":
            conversation.append(f"User: {text}")
        elif role == "assistant":
            if msg.tool_calls:
                for tc in msg.tool_calls or []:
                    fn = tc.get("function", tc) if isinstance(tc, dict) else {}
                    name = fn.get("name", "?") if isinstance(fn, dict) else "?"
                    args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
                    conversation.append(f"Assistant (tool call): {name}({args})")
            if text:
                conversation.append(f"Assistant: {text}")
        elif role == "tool":
            name = ""
            if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                name = f" (call: {msg.tool_call_id})"
            conversation.append(f"Tool result{name}: {text[:1000]}")

    if tools and require_json_tools:
        tools_prompt = TOOL_CALL_SYSTEM_PROMPT.format(tools_desc=_format_tools_for_prompt(tools))
        system_parts.append(tools_prompt)

    system_prompt = "\n".join(system_parts) if system_parts else ""

    parts: list[str] = []
    if conversation:
        parts.append("Conversation:")
        parts.extend(conversation)
        parts.append("")

    prompt = "\n".join(parts).strip()
    return prompt, system_prompt


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


def save_image(url: str) -> str | None:
    try:
        if url.startswith("data:"):
            match = re.match(r"data:image/(\w+);base64,(.+)", url)
            if not match:
                return None
            ext = match.group(1)
            data = base64.b64decode(match.group(2))
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=f".{ext}", delete=False, prefix="bridge_img_",
            ) as f:
                f.write(data)
                return f.name

        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        ext = "png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = "jpg"
        elif "gif" in content_type:
            ext = "gif"
        elif "webp" in content_type:
            ext = "webp"
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
        tools_desc_lines.append(f"  {fname}: {fdesc} | args: {json.dumps(fparams)[:300]}")
    return "\n".join(tools_desc_lines)
