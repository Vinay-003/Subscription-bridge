from __future__ import annotations

import re
from pathlib import Path

from subscription_bridge.tools.base import Tool, ToolResult

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".egg-info"}


class GrepTool(Tool):
    name = "grep"
    description = "Search for text patterns in workspace files. Returns matching file paths and line numbers."
    input_schema = {"query": "string (regex pattern)", "include": "string (optional file glob pattern)"}

    async def run(self, arguments: dict) -> ToolResult:
        query = str(arguments.get("query", ""))
        include = str(arguments.get("include", "*"))
        path_arg = str(arguments.get("path", ""))
        workspace = str(arguments.get("workspace", "."))

        if not query:
            return ToolResult(name=self.name, success=False, error="query argument is required")

        workspace_root = Path(workspace).expanduser().resolve()

        if path_arg:
            search_dir = workspace_root / path_arg
        else:
            search_dir = workspace_root

        if not search_dir.exists():
            return ToolResult(name=self.name, success=False, error=f"Path not found: {search_dir}")

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as e:
            return ToolResult(name=self.name, success=False, error=f"Invalid regex: {e}")

        results: list[str] = []
        max_results = 50

        try:
            for fpath in search_dir.rglob(include):
                if any(part in _SKIP_DIRS for part in fpath.parts):
                    continue
                if not fpath.is_file():
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for lineno, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        rel = fpath.relative_to(workspace_root)
                        results.append(f"{rel}:{lineno}: {line.rstrip()[:200]}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
        except Exception as e:
            return ToolResult(name=self.name, success=False, error=f"Search error: {e}")

        if not results:
            return ToolResult(name=self.name, success=True, output="No matches found")

        return ToolResult(
            name=self.name,
            success=True,
            output="\n".join(results),
            metadata={"matches": len(results)},
        )
