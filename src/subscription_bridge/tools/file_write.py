from __future__ import annotations

import base64
import binascii
from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class FileWriteTool(Tool):
    name = "file_write"
    description = (
        "Write content to a file in the workspace. Creates parent directories if needed. "
        "Accepts either 'content' (raw string) or 'content_base64' (base64-encoded UTF-8). "
        "For large or quote-heavy file contents, use content_base64."
    )
    input_schema = {
        "path": "string (required, file path relative to workspace)",
        "content": "string (optional, raw file content)",
        "content_base64": "string (optional, base64-encoded UTF-8 file content)",
    }

    async def run(self, arguments: dict) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        content_b64 = arguments.get("content_base64")
        workspace = str(arguments.get("workspace", "."))

        if not raw_path:
            return ToolResult(name=self.name, success=False, error="path argument is required")

        if content_b64:
            try:
                decoded = base64.b64decode(content_b64, validate=True)
                content = decoded.decode("utf-8")
            except (ValueError, binascii.Error) as e:
                return ToolResult(
                    name=self.name, success=False,
                    error=f"Invalid base64 content: {e}",
                )

        if not content and not content_b64:
            return ToolResult(
                name=self.name, success=False,
                error="either 'content' or 'content_base64' is required",
            )

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
