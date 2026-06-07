from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from subscription_bridge.core.errors import DangerousCommandError
from subscription_bridge.tools.base import Tool, ToolResult
from subscription_bridge.utils.config import load_tool_permissions
from subscription_bridge.utils.security import redact_secret

_DENY_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/"),
    re.compile(r"mkfs"),
    re.compile(r"dd\s+if="),
    re.compile(r":\(\)\s*\{"),
    re.compile(r"shutdown"),
    re.compile(r"reboot"),
    re.compile(r"poweroff"),
    re.compile(r"chmod\s+777"),
    re.compile(r"chown"),
    re.compile(r"wget\s+.*--password"),
    re.compile(r"curl\s+.*--user"),
    re.compile(r">\s+/dev/sd"),
    re.compile(r"fdisk"),
    re.compile(r"parted"),
    re.compile(r"sudo"),
    re.compile(r"passwd"),
]


class BashTool(Tool):
    name = "bash"
    description = "Run a shell command in the workspace. Captures stdout and stderr."
    input_schema = {"command": "string (shell command to execute)", "timeout": "int (optional, seconds)"}

    async def run(self, arguments: dict) -> ToolResult:
        command = str(arguments.get("command", ""))
        timeout = int(arguments.get("timeout", 30))
        workspace = str(arguments.get("workspace", "."))

        if not command:
            return ToolResult(name=self.name, success=False, error="command argument is required")

        permissions = load_tool_permissions()
        bash_config = permissions.get("bash", {})
        deny_commands = bash_config.get("deny_commands", [])

        for deny_cmd in deny_commands:
            if command.strip().startswith(deny_cmd):
                raise DangerousCommandError(command)

        for pattern in _DENY_PATTERNS:
            if pattern.search(command):
                raise DangerousCommandError(command)

        env = os.environ.copy()
        env["PWD"] = str(Path(workspace).expanduser().resolve())

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(workspace).expanduser().resolve()),
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    name=self.name,
                    success=False,
                    error=f"Command timed out after {timeout}s",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            output = stdout
            if stderr:
                output += "\n" + stderr if output else stderr

            output = redact_secret(output)

            if exit_code != 0:
                return ToolResult(
                    name=self.name,
                    success=False,
                    output=output,
                    error=f"Command exited with code {exit_code}",
                    metadata={"exit_code": exit_code},
                )

            return ToolResult(
                name=self.name,
                success=True,
                output=output,
                metadata={"exit_code": exit_code},
            )

        except DangerousCommandError:
            raise
        except Exception as e:
            return ToolResult(name=self.name, success=False, error=f"Command failed: {e}")
