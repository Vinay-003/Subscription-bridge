from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from subscription_bridge.core.plan import AgentMode, PlanState, TodoStatus


class AgentStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    NEEDS_CLARIFICATION = "needs_clarification"


@dataclass
class StepRecord:
    step_number: int
    provider_prompt_summary: str = ""
    raw_provider_response: str = ""
    parsed_action_type: str = ""
    parsed_action: dict[str, Any] | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result: str | None = None
    tool_success: bool | None = None
    timestamp: float = 0.0


@dataclass
class Observation:
    step_number: int
    action: dict[str, Any]
    tool_result: str
    tool_success: bool
    timestamp: float = 0.0


class AgentState:
    def __init__(self, task: str, workspace: str = ".", mode: AgentMode = AgentMode.ACT) -> None:
        self.run_id: str = f"run-{uuid.uuid4().hex[:12]}"
        self.task: str = task
        self.workspace: str = workspace
        self.created_at: float = time.monotonic()
        self.updated_at: float = self.created_at
        self.steps: int = 0
        self.max_steps: int = 10
        self.status: AgentStatus = AgentStatus.CREATED
        self.observations: list[Observation] = []
        self.step_records: list[StepRecord] = []
        self.final_answer: str = ""
        self.error: str = ""
        self.clarification_question: str = ""
        self.auto_file_context: str = ""
        self.plan_state: PlanState = PlanState(mode=mode)

    def start(self) -> None:
        self.status = AgentStatus.RUNNING
        self.updated_at = time.monotonic()

    def complete(self, answer: str) -> None:
        self.status = AgentStatus.COMPLETED
        self.final_answer = answer
        self.updated_at = time.monotonic()

    def fail(self, error: str) -> None:
        self.status = AgentStatus.FAILED
        self.error = error
        self.updated_at = time.monotonic()

    def exceed_max_steps(self) -> None:
        self.status = AgentStatus.MAX_STEPS_EXCEEDED
        self.error = f"Max steps ({self.max_steps}) exceeded"
        self.updated_at = time.monotonic()

    def request_clarification(self, question: str) -> None:
        self.status = AgentStatus.NEEDS_CLARIFICATION
        self.clarification_question = question
        self.updated_at = time.monotonic()

    def add_observation(self, action: dict[str, Any], result: str, success: bool) -> Observation:
        self.steps += 1
        obs = Observation(
            step_number=self.steps,
            action=dict(action),
            tool_result=result,
            tool_success=success,
            timestamp=time.monotonic(),
        )
        self.observations.append(obs)
        self.updated_at = time.monotonic()
        return obs

    def add_step_record(self, record: StepRecord) -> None:
        self.step_records.append(record)
        self.updated_at = time.monotonic()

    @property
    def recent_observations(self, count: int = 3) -> list[Observation]:
        return self.observations[-count:]

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "workspace": self.workspace,
            "status": self.status.value,
            "steps": self.steps,
            "max_steps": self.max_steps,
            "observations_count": len(self.observations),
            "final_answer": self.final_answer[:200] if self.final_answer else "",
            "error": self.error,
            "elapsed_seconds": round(time.monotonic() - self.created_at, 2),
        }

    def create_plan(self, plan_summary: str, todos: list[dict[str, str]]) -> None:
        self.plan_state.plan_summary = plan_summary
        self.plan_state.todos.clear()
        for todo_data in todos:
            content = todo_data.get("content", "")
            details = todo_data.get("details", "")
            self.plan_state.add_todo(content, details)
        self.updated_at = time.monotonic()

    def update_todo_status(self, todo_id: str, status: TodoStatus) -> bool:
        result = self.plan_state.update_todo(todo_id, status)
        self.updated_at = time.monotonic()
        return result

    def set_mode(self, mode: AgentMode) -> None:
        self.plan_state.set_mode(mode)
        self.updated_at = time.monotonic()

    @property
    def mode(self) -> AgentMode:
        return self.plan_state.mode

    def has_plan(self) -> bool:
        return self.plan_state.total_count > 0

    def get_plan_summary_for_prompt(self) -> str:
        return self.plan_state.format_for_prompt()
