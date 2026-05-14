from __future__ import annotations

from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class GlobTool(Tool):
    name = "glob"
    description = "List files matching a glob pattern in the workspace."
    input_schema = {
        "pattern": "string (glob pattern, e.g. **/*.py)",
        "path": "string (optional, directory to search from)",
    }

    async def run(self, arguments: dict) -> ToolResult:
        pattern = str(arguments.get("pattern", ""))
        workspace = str(arguments.get("workspace", "."))
        search_path = str(arguments.get("path", workspace))

        if not pattern:
            return ToolResult(name=self.name, success=False, error="pattern argument is required")

        resolved = Path(search_path).expanduser()
        if not resolved.is_absolute():
            resolved = Path(workspace).expanduser().resolve() / resolved
        workspace_root = Path(workspace).expanduser().resolve()

        try:
            resolved = resolved.resolve(strict=False)
        except (OSError, RuntimeError):
            pass

        if not str(resolved).startswith(str(workspace_root)):
            raise PathTraversalError(pattern)

        if not resolved.exists():
            return ToolResult(name=self.name, success=False, error=f"Directory not found: {search_path}")

        matches = list(resolved.rglob(pattern))
        matches = [str(m.relative_to(workspace_root)) for m in matches if m.is_file()]
        matches.sort()

        return ToolResult(
            name=self.name,
            success=True,
            output="\n".join(matches) if matches else "No files found",
            metadata={"count": len(matches), "pattern": pattern},
        )
