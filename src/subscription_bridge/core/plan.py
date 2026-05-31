from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TodoStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AgentMode(StrEnum):
    PLAN = "plan"
    ACT = "act"


@dataclass
class TodoItem:
    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "details": self.details,
        }


@dataclass
class PlanState:
    todos: list[TodoItem] = field(default_factory=list)
    mode: AgentMode = AgentMode.ACT
    plan_summary: str = ""

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self.todos if t.status == TodoStatus.PENDING)

    @property
    def completed_count(self) -> int:
        return sum(1 for t in self.todos if t.status == TodoStatus.COMPLETED)

    @property
    def total_count(self) -> int:
        return len(self.todos)

    @property
    def is_complete(self) -> bool:
        return self.total_count > 0 and self.pending_count == 0

    def add_todo(self, content: str, details: str = "") -> TodoItem:
        todo_id = f"todo-{len(self.todos) + 1}"
        todo = TodoItem(id=todo_id, content=content, details=details)
        self.todos.append(todo)
        return todo

    def update_todo(self, todo_id: str, status: TodoStatus) -> bool:
        for todo in self.todos:
            if todo.id == todo_id:
                todo.status = status
                return True
        return False

    def get_next_pending(self) -> TodoItem | None:
        for todo in self.todos:
            if todo.status == TodoStatus.PENDING:
                return todo
        return None

    def set_mode(self, mode: AgentMode) -> None:
        self.mode = mode

    def to_opencode_format(self) -> list[dict[str, Any]]:
        return [
            {
                "content": t.content,
                "status": t.status.value,
                "id": t.id,
            }
            for t in self.todos
        ]

    def format_for_prompt(self) -> str:
        if not self.todos:
            return ""
        lines = ["Current plan:", ""]
        for todo in self.todos:
            status_icon = {
                TodoStatus.PENDING: "[ ]",
                TodoStatus.IN_PROGRESS: "[~]",
                TodoStatus.COMPLETED: "[x]",
                TodoStatus.CANCELLED: "[-]",
            }[todo.status]
            lines.append(f"  {status_icon} {todo.id}: {todo.content}")
        lines.append("")
        lines.append(f"Progress: {self.completed_count}/{self.total_count} completed")
        return "\n".join(lines)
