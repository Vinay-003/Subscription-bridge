from __future__ import annotations

from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class FileEditTool(Tool):
    name = "file_edit"
    description = "Search and replace text in a file."
    input_schema = {
        "path": "string (relative path from workspace root)",
        "search": "string (text to search for)",
        "replace": "string (text to replace with)",
    }

    async def run(self, arguments: dict) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        search = str(arguments.get("search", ""))
        replace = str(arguments.get("replace", ""))
        workspace = str(arguments.get("workspace", "."))

        if not raw_path:
            return ToolResult(name=self.name, success=False, error="path argument is required")
        if not search:
            return ToolResult(name=self.name, success=False, error="search argument is required")

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
        except Exception as e:
            return ToolResult(name=self.name, success=False, error=f"Cannot read file: {e}")

        if search not in content:
            return ToolResult(name=self.name, success=False, error=f"Search text not found in file: {raw_path}")

        new_content = content.replace(search, replace, 1)
        count = content.count(search)

        try:
            resolved.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult(name=self.name, success=False, error=f"Cannot write file: {e}")

        return ToolResult(
            name=self.name,
            success=True,
            output=f"Replaced 1 occurrence in {raw_path} ({count} total occurrences of search text)",
            metadata={"path": str(resolved), "replaced": 1, "total_occurrences": count},
        )
