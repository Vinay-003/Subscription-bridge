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
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(PARSE_FAILED, reason=str(e), text_preview=text[:200])
        pass

    repaired = repair_json(text)
    try:
        return _try_direct_parse(repaired)
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        msg = (
            f"Cannot parse provider response as agent action. "
            f"After repair: {e}"
        )
        raise ParserError(raw_text=text, reason=msg) from e


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

    valid = ["tool_call", "final", "ask_clarification"]
    raise ValueError(f"Unknown action type {action_type!r}. Expected one of {valid}")


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
