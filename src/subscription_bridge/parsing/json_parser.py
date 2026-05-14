from __future__ import annotations

import json
from typing import Any

from subscription_bridge.core.errors import ParserError
from subscription_bridge.logging.events import PARSE_FAILED
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.parsing.repair import repair_json
from subscription_bridge.parsing.schemas import AgentAction

logger = get_logger(__name__)


def parse_agent_action(text: str) -> AgentAction:
    try:
        return _try_direct_parse(text)
    except json.JSONDecodeError as parse_err:
        logger.warning(PARSE_FAILED, reason=str(parse_err), text_preview=text[:200])
        pass
    except (ValueError, KeyError) as field_err:
        raise ParserError(raw_text=text, reason=str(field_err)) from field_err

    repaired = repair_json(text)
    last_error = ""
    try:
        return _try_direct_parse(repaired)
    except json.JSONDecodeError as e:
        last_error = str(e)
        pass
    except (ValueError, KeyError) as field_err:
        raise ParserError(raw_text=text, reason=str(field_err)) from field_err

    result = _regex_extract_action(text)
    if result is not None:
        logger.warning("recovered_via_regex", action_type=result.action_type, tool_name=result.tool_name)
        return result

    msg = f"Cannot parse provider response as agent action. After repair: {last_error}"
    raise ParserError(raw_text=text, reason=msg)


def _regex_extract_action(text: str) -> AgentAction | None:
    import re as _re

    if '"type":"final"' in text or '"type": "final"' in text:
        m = _re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        answer = m.group(1) if m else ""
        return AgentAction(action_type="final", answer=answer)

    if '"type":"ask_clarification"' in text or '"type": "ask_clarification"' in text:
        m_q = _re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        return AgentAction(action_type="ask_clarification", question=m_q.group(1) if m_q else "")

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
        m = _re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text, _re.DOTALL)
        if m:
            val = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
            args[key] = val

    return AgentAction(
        action_type="tool_call",
        tool_name=tool_name,
        arguments=args,
    )


def _try_direct_parse(text: str) -> AgentAction:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    action_type = data.get("type", "")
    if action_type == "tool_call":
        return _parse_tool_call(data)
    if action_type == "final":
        return _parse_final(data)
    if action_type == "ask_clarification":
        return _parse_clarification(data)

    result = _try_parse_alternative_formats(data)
    if result is not None:
        return result

    valid = ["tool_call", "final", "ask_clarification"]
    raise ValueError(f"Unknown action type {action_type!r}. Expected one of {valid}")


def _try_parse_alternative_formats(data: dict[str, Any]) -> AgentAction | None:
    from subscription_bridge.parsing.repair import try_parse_action_input

    tool_calls = data.get("tool_calls")
    if isinstance(tool_calls, list) and len(tool_calls) > 0:
        tc = tool_calls[0]
        if isinstance(tc, dict):
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            if isinstance(fn, dict):
                name = str(fn.get("name", ""))
                args_raw = fn.get("arguments", "{}")
                if isinstance(args_raw, str):
                    parsed = try_parse_action_input(args_raw)
                    if parsed is not None:
                        return AgentAction(
                            action_type="tool_call",
                            tool_name=name,
                            arguments=parsed,
                            thought=data.get("thought", ""),
                        )
                elif isinstance(args_raw, dict):
                    return AgentAction(
                        action_type="tool_call",
                        tool_name=name,
                        arguments=args_raw,
                        thought=data.get("thought", ""),
                    )

    action = data.get("action", "")
    if action:
        action_input_raw = data.get("action_input", data.get("input", "{}"))
        if isinstance(action_input_raw, str):
            parsed = try_parse_action_input(action_input_raw)
            if parsed is not None:
                return AgentAction(
                    action_type="tool_call",
                    tool_name=action,
                    arguments=parsed,
                    thought=data.get("thought", ""),
                )
        elif isinstance(action_input_raw, dict):
            return AgentAction(
                action_type="tool_call",
                tool_name=action,
                arguments=action_input_raw,
                thought=data.get("thought", ""),
            )

    return None


def _parse_tool_call(data: dict[str, Any]) -> AgentAction:
    tool_name = str(data.get("tool_name", ""))
    if not tool_name:
        raise ValueError("tool_call missing 'tool_name'")

    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError(f"arguments must be a dict, got {type(arguments).__name__}")

    return AgentAction(
        action_type="tool_call",
        thought=str(data.get("thought", "")),
        tool_name=tool_name,
        arguments=arguments,
    )


def _parse_final(data: dict[str, Any]) -> AgentAction:
    answer = str(data.get("answer", ""))
    if not answer:
        raise ValueError("final action missing 'answer'")

    return AgentAction(
        action_type="final",
        thought=str(data.get("thought", "")),
        answer=answer,
    )


def _parse_clarification(data: dict[str, Any]) -> AgentAction:
    question = str(data.get("question", ""))
    if not question:
        raise ValueError("ask_clarification action missing 'question'")

    return AgentAction(
        action_type="ask_clarification",
        thought=str(data.get("thought", "")),
        question=question,
    )
