from __future__ import annotations

from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class FileReadTool(Tool):
    name = "file_read"
    description = "Read a file from the workspace. Returns file content."
    input_schema = {"path": "string (relative path from workspace root)"}

    async def run(self, arguments: dict) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        workspace = str(arguments.get("workspace", "."))
        max_bytes = int(arguments.get("max_bytes", 1_048_576))

        if not raw_path:
            return ToolResult(name=self.name, success=False, error="path argument is required")

        resolved = Path(workspace).expanduser().resolve() / raw_path
        workspace_root = Path(workspace).expanduser().resolve()

        try:
            resolved = resolved.resolve(strict=False)
        except (OSError, RuntimeError):
            pass

        if not str(resolved).startswith(str(workspace_root)):
            raise PathTraversalError(raw_path)

        if not resolved.exists():
            return ToolResult(name=self.name, success=False, error=f"File not found: {raw_path}")

        if not resolved.is_file():
            return ToolResult(name=self.name, success=False, error=f"Not a file: {raw_path}")

        try:
            content = resolved.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            return ToolResult(name=self.name, success=False, error=f"Cannot read file: {e}")

        if len(content) > max_bytes:
            content = content[:max_bytes] + f"\n... (truncated at {max_bytes} bytes)"

        return ToolResult(
            name=self.name,
            success=True,
            output=content,
            metadata={"path": str(resolved), "size_bytes": len(content)},
        )
