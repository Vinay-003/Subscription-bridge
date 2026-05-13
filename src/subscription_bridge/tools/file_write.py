from __future__ import annotations

from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class FileWriteTool(Tool):
    name = "file_write"
    description = "Write content to a file in the workspace. Creates parent directories if needed."
    input_schema = {"path": "string", "content": "string"}

    async def run(self, arguments: dict) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        workspace = str(arguments.get("workspace", "."))

        if not raw_path:
            return ToolResult(name=self.name, success=False, error="path argument is required")

        resolved = Path(workspace).expanduser().resolve() / raw_path
        workspace_root = Path(workspace).expanduser().resolve()

        try:
            resolved = resolved.resolve()
        except (OSError, RuntimeError):
            resolved = (workspace_root / raw_path).resolve()

        if not str(resolved).startswith(str(workspace_root)):
            raise PathTraversalError(raw_path)

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(name=self.name, success=False, error=f"Cannot write file: {e}")

        return ToolResult(
            name=self.name,
            success=True,
            output=f"Written {len(content)} bytes to {raw_path}",
            metadata={"path": str(resolved), "bytes_written": len(content)},
        )
