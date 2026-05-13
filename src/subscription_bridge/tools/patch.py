from __future__ import annotations

import asyncio
from pathlib import Path

from subscription_bridge.tools.base import Tool, ToolResult


class PatchTool(Tool):
    name = "patch"
    description = "Apply a unified diff to files in the workspace. Prefers git apply."
    input_schema = {"diff": "string (unified diff text)"}

    async def run(self, arguments: dict) -> ToolResult:
        diff_text = str(arguments.get("diff", ""))
        workspace = str(arguments.get("workspace", "."))

        if not diff_text:
            return ToolResult(name=self.name, success=False, error="diff argument is required")

        workspace_root = Path(workspace).expanduser().resolve()
        git_dir = workspace_root / ".git"

        if git_dir.exists():
            try:
                proc = await asyncio.create_subprocess_shell(
                    "git apply",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workspace_root),
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=diff_text.encode("utf-8")), timeout=30
                )
                exit_code = proc.returncode or 0

                if exit_code == 0:
                    return ToolResult(
                        name=self.name,
                        success=True,
                        output="Patch applied successfully via git apply",
                    )

                stderr = stderr_bytes.decode("utf-8", errors="replace")
                return ToolResult(
                    name=self.name,
                    success=False,
                    output="git apply failed (trying patch command)",
                    error=stderr,
                )
            except Exception:
                pass

        try:
            proc = await asyncio.create_subprocess_shell(
                "patch -p1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_root),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=diff_text.encode("utf-8")), timeout=30
            )
            exit_code = proc.returncode or 0

            if exit_code == 0:
                return ToolResult(
                    name=self.name,
                    success=True,
                    output="Patch applied successfully via patch command",
                )

            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return ToolResult(
                name=self.name,
                success=False,
                error=f"Patch failed: {stderr}",
            )

        except Exception as e:
            return ToolResult(name=self.name, success=False, error=f"Patch error: {e}")
