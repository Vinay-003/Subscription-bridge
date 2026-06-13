from __future__ import annotations

import json
import re
from typing import Any

from subscription_bridge.api.openai_models import FunctionCall, ToolCall
from subscription_bridge.parsing.repair import (
    extract_first_json,
    repair_json,
    strip_code_fences,
)


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Parse tool calls out of unreliable browser-LLM output.

    Browser models rarely emit a clean OpenAI tool-call object: they wrap JSON
    in prose, use Markdown fences, emit multiple fenced blocks, leave trailing
    commas / smart quotes / unescaped newlines, or use the LangChain-style
    ``action`` / ``action_input`` shape. We try a series of candidates, each
    run through the shared JSON repair pipeline, and return the first that
    yields at least one valid tool call.
    """
    text = text.strip()
    if not text:
        return []

    # 1. <tool_call>...</tool_call> XML wrappers (one or more).
    xml_result = _parse_xml_tool_calls(text)
    if xml_result:
        return xml_result

    # 2. Try every candidate string against the JSON pipeline. Order matters:
    #    fenced blocks first (most explicit), then the first embedded JSON
    #    object, then repaired variants, then the whole text.
    for candidate in _json_candidates(text):
        result = _tool_calls_from_text(candidate)
        if result:
            return result

    # 3. Last resort: the model emitted a tool call whose argument string holds
    #    raw, unescaped code (unescaped quotes / literal newlines), which no
    #    JSON parser can load. Reconstruct it structurally from the key anchors.
    recovered = _recover_toolcall_with_raw_args(text)
    if recovered:
        return recovered

    return []


def _json_candidates(text: str) -> list[str]:
    """Build an ordered, de-duplicated list of strings worth attempting."""
    candidates: list[str] = []

    # Each fenced code block, in order of appearance.
    candidates.extend(_code_block_contents(text))

    # The first balanced {...} object embedded anywhere in the text.
    candidates.append(extract_first_json(text))

    # Fences stripped, then the full repair pipeline.
    candidates.append(strip_code_fences(text))
    candidates.append(repair_json(text))

    # The raw text last.
    candidates.append(text)

    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        s = (c or "").strip()
        if s and s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _code_block_contents(text: str) -> list[str]:
    return [m.strip() for m in re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)]


def _tool_calls_from_text(candidate: str) -> list[ToolCall]:
    """Attempt to load ``candidate`` as JSON (with repair) and extract calls."""
    data = _loads_with_repair(candidate)
    if data is None:
        return []
    return _tool_calls_from_json_value(data)


def _loads_with_repair(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        pass
    repaired = repair_json(candidate)
    if repaired and repaired != candidate:
        try:
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


# Argument keys whose values are commonly code/multiline and therefore the
# usual culprits for unescaped quotes and raw newlines.
_RAW_ARG_KEYS = (
    "content",
    "command",
    "new_string",
    "old_string",
    "replace",
    "search",
    "patch",
    "body",
)
_SCALAR_ARG_KEYS = ("filePath", "file_path", "path", "pattern", "query", "workdir")


def _recover_toolcall_with_raw_args(text: str) -> list[ToolCall]:
    """Reconstruct a single tool call from output with unescaped raw arguments.

    Strategy: find the function name, then for each known argument key locate
    its value. Code-like keys are extracted by scanning from the opening quote
    to the quote that is actually followed by a JSON delimiter, treating the
    body as a literal (so embedded quotes/newlines are preserved). Scalar keys
    use a simple non-greedy match.
    """
    name_match = re.search(r'"name"\s*:\s*"([A-Za-z0-9_.\-]+)"', text)
    if not name_match:
        return []
    name = name_match.group(1)

    args: dict[str, Any] = {}
    for key in _RAW_ARG_KEYS:
        value = _extract_raw_string_value(text, key)
        if value is not None:
            args[key] = value
    for key in _SCALAR_ARG_KEYS:
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"\n]*)"', text)
        if m:
            args[key] = m.group(1)

    if not args:
        return []

    call_id = ""
    id_match = re.search(r'"id"\s*:\s*"([^"\n]+)"', text)
    if id_match:
        call_id = id_match.group(1)

    return [
        ToolCall(
            id=call_id,
            type="function",
            function=FunctionCall(name=name, arguments=json.dumps(args)),
        )
    ]


def _extract_raw_string_value(text: str, key: str) -> str | None:
    """Extract a string value that may contain unescaped quotes and newlines.

    Finds `"key" :` then the opening quote of the value, and scans forward to
    the closing quote: the first `"` that is followed (ignoring whitespace) by
    a `,` or `}` which in turn precedes another key or the object end. Embedded
    quotes are kept verbatim in the returned (decoded) string.
    """
    key_match = re.search(rf'"{re.escape(key)}"\s*:\s*"', text)
    if not key_match:
        return None
    start = key_match.end()  # first char after the opening quote

    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == '"':
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j >= n or text[j] in (",", "}"):
                # Likely the real terminator: a delimiter follows. Accept it
                # unless what follows the delimiter clearly continues a string
                # value (heuristic kept simple: a following key or object end).
                raw = text[start:i]
                return _decode_loose(raw)
        i += 1
    return None


def _decode_loose(raw: str) -> str:
    """Turn a loosely-captured JSON string body into the intended text."""
    return (
        raw.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _parse_xml_tool_calls(text: str) -> list[ToolCall]:
    raw_calls = re.findall(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
    result: list[ToolCall] = []
    for raw in raw_calls:
        data = _loads_with_repair(raw.strip())
        if isinstance(data, dict):
            result.append(_to_tool_call(_ensure_function_wrapper(data)))
    return result


def _tool_calls_from_json_value(data: Any) -> list[ToolCall]:
    # {"tool_calls": [...]}
    if isinstance(data, dict) and "tool_calls" in data:
        raw = data["tool_calls"]
        raw_list = list(raw) if isinstance(raw, list) else []
        return [
            _to_tool_call(_ensure_function_wrapper(tc))
            for tc in raw_list
            if isinstance(tc, dict)
        ]
    # Bare list of calls.
    if isinstance(data, list):
        return [
            _to_tool_call(_ensure_function_wrapper(tc))
            for tc in data
            if isinstance(tc, dict)
        ]
    if isinstance(data, dict):
        # {"name": ..., "arguments": ...} or {"function": {...}}
        if "name" in data or "function" in data:
            return [_to_tool_call(_ensure_function_wrapper(data))]
        # LangChain-style {"action": "tool", "action_input": {...}}
        if "action" in data and isinstance(data["action"], str):
            return [_to_tool_call(_ensure_function_wrapper(_from_action_format(data)))]
    return []


def _from_action_format(data: dict[str, Any]) -> dict[str, Any]:
    args = data.get("action_input", data.get("input", {}))
    return {
        "id": data.get("id", ""),
        "name": data["action"],
        "arguments": args,
    }


def _to_tool_call(data: dict[str, Any]) -> ToolCall:
    fn = data.get("function", {})
    if isinstance(fn, dict):
        args = fn.get("arguments", "{}")
        if not isinstance(args, str):
            args = json.dumps(args)
        return ToolCall(
            id=data.get("id", ""),
            type=data.get("type", "function"),
            function=FunctionCall(name=fn.get("name", ""), arguments=args),
        )
    return ToolCall(
        id=data.get("id", ""),
        type="function",
        function=FunctionCall(
            name=data.get("name", ""),
            arguments=json.dumps(data.get("arguments", {})),
        ),
    )


def _ensure_function_wrapper(data: dict[str, Any]) -> dict[str, Any]:
    if "function" not in data and "name" in data:
        args = data.get("arguments", {})
        if not isinstance(args, str):
            args = json.dumps(args)
        return {
            "id": data.get("id", ""),
            "type": "function",
            "function": {
                "name": data["name"],
                "arguments": args,
            },
        }
    return data
