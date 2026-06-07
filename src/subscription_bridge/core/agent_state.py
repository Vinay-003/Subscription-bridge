from __future__ import annotations

import hashlib
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
    STUCK = "stuck"


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
    tool_error: str = ""


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

    def mark_stuck(self, message: str) -> None:
        self.status = AgentStatus.STUCK
        self.error = message
        self.updated_at = time.monotonic()

    def fingerprint_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Stable hash of a tool call, used by the stuck-loop detector.

        Only fields that affect what the model will see on disk matter:
        - bash: 'command'
        - file_write / patch: 'content' or 'diff'
        - file_edit: 'search' + 'replace'
        - everything else: full JSON dump of arguments
        """
        key_fields = {
            "bash": ("command",),
            "file_write": ("path", "content"),
            "patch": ("diff",),
            "file_edit": ("path", "search", "replace"),
        }
        fields = key_fields.get(tool_name)
        if fields:
            payload = {k: arguments.get(k, "") for k in fields}
        else:
            payload = arguments
        import json
        try:
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            raw = repr(payload)
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]

    def is_stuck(self, tool_name: str, arguments: dict[str, Any], threshold: int = 3) -> bool:
        """Return True if the model has issued the *same* tool call at least
        `threshold` times in a row (most recent observations).

        This catches the failure mode where a model re-issues the same
        broken command and never makes progress — e.g. a bash heredoc with
        the same syntactic error, or a file_write with the same broken
        content. The loop is broken with a STUCK status before
        `max_steps` is exhausted so the user gets a clear failure message
        rather than a hallucinated "final" answer.
        """
        if not self.observations:
            return False
        current_fp = self.fingerprint_tool_call(tool_name, arguments)
        consecutive = 0
        for obs in reversed(self.observations):
            prev_tool = (obs.action or {}).get("tool_name", "")
            prev_args = (obs.action or {}).get("arguments", {}) or {}
            if prev_tool != tool_name:
                break
            prev_fp = self.fingerprint_tool_call(tool_name, prev_args)
            if prev_fp != current_fp:
                break
            consecutive += 1
            if consecutive >= threshold:
                return True
        return False

    def is_repeating_tool_failure(self, threshold: int = 3) -> bool:
        """Return True if the last `threshold` tool calls ALL failed with
        similar (non-empty) error output. Used to detect when a model is
        about to emit a hallucinated 'final' answer after a string of
        failed attempts, e.g. emitting "calculator created successfully"
        after 3 consecutive gcc errors.
        """
        if len(self.observations) < threshold:
            return False
        recent = self.observations[-threshold:]
        for obs in recent:
            if obs.tool_success:
                return False
            if not (obs.tool_error or "").strip() and not (obs.tool_result or "").strip():
                return False
        return True

    def add_observation(
        self, action: dict[str, Any], result: str, success: bool, error: str = "",
    ) -> Observation:
        self.steps += 1
        obs = Observation(
            step_number=self.steps,
            action=dict(action),
            tool_result=result,
            tool_success=success,
            timestamp=time.monotonic(),
            tool_error=error,
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
