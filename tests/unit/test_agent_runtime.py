from __future__ import annotations

import pytest

from subscription_bridge.core import AgentRuntime, Task
from subscription_bridge.providers.fake import FakeProviderAdapter
from subscription_bridge.tools import FileReadTool, GrepTool, ToolRegistry


def _scripted_provider(responses: list[str]) -> FakeProviderAdapter:
    return FakeProviderAdapter(scripted_responses=responses)


def _tool_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(FileReadTool())
    r.register(GrepTool())
    return r


@pytest.mark.asyncio
async def test_runtime_tool_call_then_final() -> None:
    provider = _scripted_provider([
        '{"type":"tool_call","thought":"need info","tool_name":"file_read","arguments":{"path":"README.md"}}',
        '{"type":"final","thought":"done","answer":"The answer is 42"}',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert result.success
    assert result.answer == "The answer is 42"
    assert result.steps == 2


@pytest.mark.asyncio
async def test_runtime_max_steps_exceeded() -> None:
    provider = _scripted_provider([
        '{"type":"tool_call","thought":"need info","tool_name":"file_read","arguments":{"path":"README.md"}}',
        '{"type":"tool_call","thought":"need more","tool_name":"file_read","arguments":{"path":"README.md"}}',
        '{"type":"tool_call","thought":"need more","tool_name":"file_read","arguments":{"path":"README.md"}}',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=2)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert not result.success
    assert "exceeded" in result.error


@pytest.mark.asyncio
async def test_runtime_final_answer_direct() -> None:
    provider = _scripted_provider([
        '{"type":"final","thought":"done","answer":"Simple answer"}',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert result.success
    assert result.answer == "Simple answer"
    assert result.steps == 1


@pytest.mark.asyncio
async def test_runtime_clarification() -> None:
    provider = _scripted_provider([
        '{"type":"ask_clarification","thought":"unclear","question":"What exactly do you want?"}',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="vague task", workspace=".")
    result = await runtime.run(task)
    assert not result.success
    assert result.needs_clarification
    assert "What exactly" in result.question


@pytest.mark.asyncio
async def test_runtime_parser_plain_text_fallback() -> None:
    provider = _scripted_provider([
        'this is not json at all',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert result.success
    assert result.answer == "this is not json at all"


@pytest.mark.asyncio
async def test_runtime_unknown_tool_handled() -> None:
    provider = _scripted_provider([
        '{"type":"tool_call","thought":"need info","tool_name":"nonexistent_tool","arguments":{}}',
        '{"type":"final","thought":"done","answer":"recovered"}',
    ])
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert result.success
    assert result.answer == "recovered"


@pytest.mark.asyncio
async def test_runtime_provider_failure() -> None:
    provider = FakeProviderAdapter(fail_rate=1.0)
    runtime = AgentRuntime(provider=provider, tool_registry=_tool_registry(), max_steps=5)
    task = Task(text="test task", workspace=".")
    result = await runtime.run(task)
    assert not result.success
    assert "Provider" in result.error or "error" in result.error.lower()
