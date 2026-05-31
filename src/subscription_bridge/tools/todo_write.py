from __future__ import annotations

from subscription_bridge.tools.base import Tool, ToolResult


class TodoWriteTool(Tool):
    name = "todo_write"
    description = "Create or update todos. Use this to track task progress. Opencode will display these todos in the UI."
    input_schema = {
        "todos": "array of objects with content (string), status (pending|in_progress|completed|cancelled), and optional id (string)"
    }

    async def run(self, arguments: dict) -> ToolResult:
        todos = arguments.get("todos", [])
        if not isinstance(todos, list):
            return ToolResult(
                name=self.name,
                success=False,
                error="todos must be an array of objects",
            )

        if not todos:
            return ToolResult(
                name=self.name,
                success=False,
                error="todos array cannot be empty",
            )

        output_lines = ["Todos updated:"]
        for i, todo in enumerate(todos, 1):
            content = todo.get("content", "")
            status = todo.get("status", "pending")
            todo_id = todo.get("id", f"todo-{i}")

            if status not in ["pending", "in_progress", "completed", "cancelled"]:
                status = "pending"

            status_icon = {
                "pending": "[ ]",
                "in_progress": "[~]",
                "completed": "[x]",
                "cancelled": "[-]",
            }[status]

            output_lines.append(f"  {status_icon} {todo_id}: {content}")

        return ToolResult(
            name=self.name,
            success=True,
            output="\n".join(output_lines),
            metadata={"todos": todos},
        )
