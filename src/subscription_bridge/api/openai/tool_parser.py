from __future__ import annotations

import json
import re
from typing import Any

from subscription_bridge.api.openai_models import FunctionCall, ToolCall


def parse_tool_calls(text: str) -> list[ToolCall]:
    text = text.strip()
    if not text:
        return []

    xml_result = _parse_xml_tool_calls(text)
    if xml_result:
        return xml_result

    json_result = _parse_json_tool_calls(text)
    if json_result:
        return json_result

    code_block_result = _parse_code_block_tool_calls(text)
    if code_block_result:
        return code_block_result

    return _parse_regex_tool_calls(text)


def _parse_xml_tool_calls(text: str) -> list[ToolCall]:
    raw_calls = re.findall(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
    result: list[ToolCall] = []
    for raw in raw_calls:
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            result.append(_to_tool_call(_ensure_function_wrapper(data)))
    return result


def _parse_json_tool_calls(text: str) -> list[ToolCall]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _tool_calls_from_json_value(data)


def _parse_code_block_tool_calls(text: str) -> list[ToolCall]:
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if not code_block:
        return []
    try:
        data = json.loads(code_block.group(1).strip())
    except json.JSONDecodeError:
        return []
    return _tool_calls_from_json_value(data)


def _parse_regex_tool_calls(text: str) -> list[ToolCall]:
    patterns = [
        r'\{[^{}]*"function"[^{}]*\{[^}]*\}[^{}]*\}',
        r'\{[^{}]*"tool_calls"[^{}]*\}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        result = _tool_calls_from_json_value(data)
        if result:
            return result
    return []


def _tool_calls_from_json_value(data: Any) -> list[ToolCall]:
    if isinstance(data, dict) and "tool_calls" in data:
        raw = data["tool_calls"]
        raw_list = list(raw) if isinstance(raw, list) else []
        return [_to_tool_call(_ensure_function_wrapper(tc)) for tc in raw_list if isinstance(tc, dict)]
    if isinstance(data, list):
        return [_to_tool_call(_ensure_function_wrapper(tc)) for tc in data if isinstance(tc, dict)]
    if isinstance(data, dict) and ("name" in data or "function" in data):
        return [_to_tool_call(_ensure_function_wrapper(data))]
    return []


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
        return {
            "id": data.get("id", ""),
            "type": "function",
            "function": {
                "name": data["name"],
                "arguments": json.dumps(data.get("arguments", {})),
            },
        }
    return data
