from __future__ import annotations

from subscription_bridge.core.agent_state import AgentState, AgentStatus


def test_initial_state() -> None:
    state = AgentState(task="test task", workspace=".")
    assert state.run_id.startswith("run-")
    assert state.task == "test task"
    assert state.status == AgentStatus.CREATED
    assert state.steps == 0


def test_start() -> None:
    state = AgentState(task="test", workspace=".")
    state.start()
    assert state.status == AgentStatus.RUNNING


def test_complete() -> None:
    state = AgentState(task="test", workspace=".")
    state.complete("final answer")
    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer == "final answer"


def test_fail() -> None:
    state = AgentState(task="test", workspace=".")
    state.fail("something went wrong")
    assert state.status == AgentStatus.FAILED
    assert state.error == "something went wrong"


def test_exceed_max_steps() -> None:
    state = AgentState(task="test", workspace=".")
    state.exceed_max_steps()
    assert state.status == AgentStatus.MAX_STEPS_EXCEEDED


def test_request_clarification() -> None:
    state = AgentState(task="test", workspace=".")
    state.request_clarification("What do you mean?")
    assert state.status == AgentStatus.NEEDS_CLARIFICATION
    assert state.clarification_question == "What do you mean?"


def test_add_observation_increments_steps() -> None:
    state = AgentState(task="test", workspace=".")
    obs = state.add_observation(
        action={"tool_name": "file_read", "arguments": {"path": "x.txt"}},
        result="content",
        success=True,
    )
    assert state.steps == 1
    assert obs.step_number == 1
    assert obs.tool_result == "content"


def test_summary_includes_key_fields() -> None:
    state = AgentState(task="my task", workspace=".")
    state.start()
    state.complete("done")
    summary = state.summary
    assert summary["run_id"] == state.run_id
    assert summary["task"] == "my task"
    assert summary["status"] == "completed"
    assert "elapsed_seconds" in summary
