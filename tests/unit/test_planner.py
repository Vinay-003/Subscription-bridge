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
    assert "tool_call" in prompt


def test_system_prompt_empty_tools() -> None:
    prompt = build_system_prompt([])
    assert "tool_call" in prompt


def test_system_prompt_is_agentic() -> None:
    """The prompt must tell the model to call tools for file creation tasks,
    not just describe the code in the 'answer' field. This is the main
    defense against models that try to be helpful by responding with prose
    instead of using the available tools.
    """
    prompt = build_system_prompt([
        {"name": "file_write", "description": "Write file", "input_schema": {"path": "string", "content": "string"}},
        {"name": "bash", "description": "Run shell", "input_schema": {"command": "string"}},
    ])
    assert "AGENTIC" in prompt
    assert "MUST call a tool" in prompt
    assert "MUST use the file_write" in prompt
    assert "MUST use the bash" in prompt
    assert "NEVER just describe" in prompt


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
