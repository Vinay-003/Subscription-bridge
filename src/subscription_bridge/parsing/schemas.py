from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class ToolCallAction(BaseModel):
    type: str = "tool_call"
    thought: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = {}

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "tool_call":
            raise ValueError(f"Expected 'tool_call', got {v!r}")
        return v


class FinalAction(BaseModel):
    type: str = "final"
    thought: str = ""
    answer: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "final":
            raise ValueError(f"Expected 'final', got {v!r}")
        return v


class AskClarificationAction(BaseModel):
    type: str = "ask_clarification"
    thought: str = ""
    question: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "ask_clarification":
            raise ValueError(f"Expected 'ask_clarification', got {v!r}")
        return v


class AgentAction(BaseModel):
    action_type: str
    thought: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = {}
    answer: str = ""
    question: str = ""

    @classmethod
    def from_tool_call(cls, data: dict[str, Any]) -> AgentAction:
        validated = ToolCallAction(**data)
        return cls(
            action_type="tool_call",
            thought=validated.thought,
            tool_name=validated.tool_name,
            arguments=validated.arguments,
        )

    @classmethod
    def from_final(cls, data: dict[str, Any]) -> AgentAction:
        validated = FinalAction(**data)
        return cls(
            action_type="final",
            thought=validated.thought,
            answer=validated.answer,
        )

    @classmethod
    def from_clarification(cls, data: dict[str, Any]) -> AgentAction:
        validated = AskClarificationAction(**data)
        return cls(
            action_type="ask_clarification",
            thought=validated.thought,
            question=validated.question,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentAction:
        action_type = data.get("type", "")
        if action_type == "tool_call":
            return cls.from_tool_call(data)
        if action_type == "final":
            return cls.from_final(data)
        if action_type == "ask_clarification":
            return cls.from_clarification(data)
        valid_types = ["tool_call", "final", "ask_clarification"]
        raise ValueError(f"Unknown action type {action_type!r}. Expected one of {valid_types}")
