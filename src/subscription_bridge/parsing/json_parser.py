from __future__ import annotations

import json
from typing import Any

from subscription_bridge.core.errors import ParserError
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.parsing.repair import (
    extract_first_json,
    repair_json,
    strip_code_fences,
    try_parse_action_input,
)
from subscription_bridge.parsing.schemas import AgentAction

logger = get_logger(__name__)


def parse_agent_action(text: str) -> AgentAction:
    candidates = _build_candidates(text)

    for idx, candidate in enumerate(candidates):
        if not candidate or not candidate.strip():
            continue
        result = _try_parse_candidate(candidate)
        if result is not None:
            if idx > 0:
                logger.info(
                    "parser_candidate_accepted",
                    candidate_index=idx,
                    text_preview=candidate[:120],
                )
            return result

    result = _plain_text_fallback(text)
    if result is not None:
        logger.info("parser_plain_text_fallback", text_preview=text[:120])
        return result

    msg = "Cannot parse provider response as agent action"
    raise ParserError(raw_text=text, reason=msg)


def _build_candidates(text: str) -> list[str]:
    candidates: list[str] = []

    candidates.append(text)
    candidates.append(strip_code_fences(text))
    candidates.append(extract_first_json(text))
    candidates.append(repair_json(text))

    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        s = c.strip()
        if s and s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _try_parse_candidate(text: str) -> AgentAction | None:
    result = _try_direct_parse(text)
    if result is not None:
        return result

    result = _try_openai_tool_calls(text)
    if result is not None:
        return result

    result = _try_alternative_format_parse(text)
    if result is not None:
        return result

    result = _regex_extract_action(text)
    if result is not None:
        logger.warning("recovered_via_regex", action_type=result.action_type, tool_name=result.tool_name)
        return result

    return None


def _try_direct_parse(text: str) -> AgentAction | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    raw_args = data.get("arguments", {})
    if isinstance(raw_args, str):
        parsed = try_parse_action_input(raw_args)
        if parsed is not None:
            data["arguments"] = parsed
        else:
            data["arguments"] = {"raw": raw_args}
    elif isinstance(raw_args, dict):
        data["arguments"] = _normalize_arguments(raw_args)

    try:
        action = AgentAction.from_dict(data)
    except (ValueError, KeyError):
        return None

    if action.action_type == "tool_call" and not action.tool_name:
        return None
    if action.action_type == "final" and not action.answer:
        return None
    if action.action_type == "ask_clarification" and not action.question:
        return None

    return action


def _normalize_arguments(args: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, (int, float, bool)):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def _try_openai_tool_calls(text: str) -> AgentAction | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    tool_calls = data.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) == 0:
        return None

    tc = tool_calls[0]
    if not isinstance(tc, dict):
        return None

    fn = tc.get("function", {})
    if not isinstance(fn, dict):
        return None

    name = str(fn.get("name", ""))
    if not name:
        return None

    args_raw = fn.get("arguments", "{}")
    parsed: dict[str, Any] = {}
    if isinstance(args_raw, str):
        p = try_parse_action_input(args_raw)
        if p is not None:
            parsed = p
        else:
            parsed = {"raw": args_raw}
    elif isinstance(args_raw, dict):
        parsed = args_raw

    return AgentAction(
        action_type="tool_call",
        tool_name=name,
        arguments=parsed,
        thought=data.get("thought", ""),
    )


def _try_alternative_format_parse(text: str) -> AgentAction | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    action = data.get("action", "")
    if not action:
        return None

    action_input_raw = data.get("action_input", data.get("input", "{}"))
    parsed: dict[str, Any] = {}
    if isinstance(action_input_raw, str):
        p = try_parse_action_input(action_input_raw)
        if p is not None:
            parsed = p
        else:
            parsed = {"raw": action_input_raw}
    elif isinstance(action_input_raw, dict):
        parsed = action_input_raw

    return AgentAction(
        action_type="tool_call",
        tool_name=action,
        arguments=parsed,
        thought=data.get("thought", ""),
    )


def _plain_text_fallback(text: str) -> AgentAction | None:
    clean = text.strip()
    if not clean:
        return None
    return AgentAction(action_type="final", answer=clean)


def _regex_extract_action(text: str) -> AgentAction | None:
    import re as _re

    def _extract_loose_string_value(source: str, key: str) -> str | None:
        key_match = _re.search(rf'"{key}"\s*:', source)
        if not key_match:
            return None
        idx = key_match.end()
        while idx < len(source) and source[idx].isspace():
            idx += 1
        if idx >= len(source) or source[idx] != '"':
            return None
        idx += 1
        result: list[str] = []
        escape_next = False
        while idx < len(source):
            ch = source[idx]
            if escape_next:
                result.append(ch)
                escape_next = False
                idx += 1
                continue
            if ch == "\\":
                result.append(ch)
                escape_next = True
                idx += 1
                continue
            if ch == '"':
                look = idx + 1
                while look < len(source) and source[look].isspace():
                    look += 1
                if look >= len(source) or source[look] in (",", "}"):
                    break
                result.append('"')
                idx += 1
                continue
            result.append(ch)
            idx += 1
        if not result:
            return None
        val = "".join(result)
        return val.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")

    if '"type":"final"' in text or '"type": "final"' in text:
        m = _re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        answer = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t") if m else ""
        if not answer:
            return None
        return AgentAction(action_type="final", answer=answer)

    if '"type":"ask_clarification"' in text or '"type": "ask_clarification"' in text:
        m_q = _re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        question = m_q.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t") if m_q else ""
        if not question:
            return None
        return AgentAction(action_type="ask_clarification", question=question)

    m_tool = _re.search(r'"tool_name"\s*:\s*"(\w+)"', text)
    if not m_tool:
        m_tool = _re.search(r'"name"\s*:\s*"(\w+)"', text)
    if not m_tool:
        m_tool = _re.search(r'"action"\s*:\s*"(\w+)"', text)
    if not m_tool:
        return None

    tool_name = m_tool.group(1)
    args: dict[str, str] = {}

    for key in ("path", "search", "replace", "content", "command", "pattern", "query", "question"):
        loose_keys = ("content", "command", "replace", "search")
        if key in loose_keys:
            loose = _extract_loose_string_value(text, key)
            if loose is not None:
                args[key] = loose
                continue
        m = _re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        if m:
            val = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
            args[key] = val

    return AgentAction(
        action_type="tool_call",
        tool_name=tool_name,
        arguments=args,
    )
