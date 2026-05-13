from __future__ import annotations

import asyncio
from pathlib import Path

from subscription_bridge.tools.base import Tool, ToolResult


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show uncommitted git changes in the workspace. Returns unified diff text."
    input_schema = {}

    async def run(self, arguments: dict) -> ToolResult:
        workspace = str(arguments.get("workspace", "."))
        workspace_root = Path(workspace).expanduser().resolve()

        git_dir = workspace_root / ".git"
        if not git_dir.exists():
            return ToolResult(
                name=self.name,
                success=True,
                output="Not a git repository or no .git directory found.",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                "git diff",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_root),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=15
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")

            output = stdout
            if not output:
                output = "(no uncommitted changes)"

            return ToolResult(
                name=self.name,
                success=True,
                output=output,
                metadata={"has_changes": bool(stdout.strip())},
            )

        except Exception as e:
            return ToolResult(
                name=self.name,
                success=False,
                error=f"git diff failed: {e}",
            )
