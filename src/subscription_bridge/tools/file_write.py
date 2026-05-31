from __future__ import annotations

from pathlib import Path

from subscription_bridge.core.errors import PathTraversalError
from subscription_bridge.tools.base import Tool, ToolResult


class FileWriteTool(Tool):
    name = "file_write"
    description = (
        "Write content to a file in the workspace. Creates parent directories if needed. "
        "Use 'content' with the raw string to write. "
        "For large files (>200 lines), use bash with a heredoc instead."
    )
    input_schema = {
        "path": "string (required, file path relative to workspace)",
        "content": "string (required, raw file content — escape newlines as \\n, quotes as \\\")",
    }

    async def run(self, arguments: dict) -> ToolResult:
        raw_path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        content_b64 = arguments.get("content_base64")
        workspace = str(arguments.get("workspace", "."))

        if not raw_path:
            return ToolResult(name=self.name, success=False, error="path argument is required")

        if content_b64:
            import base64 as _b64
            import binascii as _bin
            try:
                decoded = _b64.b64decode(content_b64, validate=True)
                content = decoded.decode("utf-8")
            except (ValueError, _bin.Error) as e:
                return ToolResult(
                    name=self.name, success=False,
                    error=f"Invalid base64 content: {e}",
                )

        if not content and not content_b64:
            return ToolResult(
                name=self.name, success=False,
                error="either 'content' or 'content_base64' is required",
            )

        _GARBAGE_PATTERNS = {"YmFzZTY0", "base64", ""}
        if content.strip() in _GARBAGE_PATTERNS and len(content.strip()) < 20:
            return ToolResult(
                name=self.name, success=False,
                error=(
                    "Refusing to write garbage content. "
                    "The content field contains only a placeholder, not actual file content. "
                    "Use 'content' with the full raw string, or use bash with a heredoc for large files."
                ),
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
