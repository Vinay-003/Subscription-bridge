from __future__ import annotations

from subscription_bridge.core.agent_state import AgentState
from subscription_bridge.core.planner import build_observation_context, build_system_prompt, build_user_prompt


def test_system_prompt_includes_tools() -> None:
    tools = [
        {"name": "file_read", "description": "Read a file", "input_schema": {"path": "string"}},
        {"name": "grep", "description": "Search text", "input_schema": {"query": "string"}},
    ]
    prompt = build_system_prompt(tools)
    assert "file_read" in prompt
    assert "grep" in prompt
    assert "STRICT JSON" in prompt
    assert "tool_call" in prompt
    assert "final" in prompt


def test_system_prompt_empty_tools() -> None:
    prompt = build_system_prompt([])
    assert "STRICT JSON" in prompt


def test_user_prompt_includes_task() -> None:
    state = AgentState(task="read README and summarize", workspace=".")
    prompt = build_user_prompt(state)
    assert "read README and summarize" in prompt


def test_user_prompt_with_observations() -> None:
    state = AgentState(task="test task", workspace=".")
    state.add_observation(
        action={"tool_name": "file_read", "arguments": {"path": "test.txt"}},
        result="file content here",
        success=True,
    )
    prompt = build_user_prompt(state)
    assert "file_read" in prompt
    assert "test.txt" in prompt or "file content" in prompt


def test_observation_context_empty() -> None:
    state = AgentState(task="test", workspace=".")
    ctx = build_observation_context(state)
    assert ctx == ""
