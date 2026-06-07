from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from subscription_bridge.core.errors import ToolNotFoundError
from subscription_bridge.logging.events import TOOL_CALLED, TOOL_COMPLETED
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.tools.base import ToolResult
from subscription_bridge.tools.registry import ToolRegistry
from subscription_bridge.utils.config import load_tool_permissions
from subscription_bridge.utils.security import sanitize_for_log

logger = get_logger(__name__)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, workspace: str = ".") -> None:
        self._registry = registry
        resolved = os.path.abspath(os.path.expanduser(workspace or "."))
        self._workspace = resolved
        if workspace == "." or not workspace:
            logger.warning(
                "tool_workspace_default_fallback",
                workspace=self._workspace,
                note="no workspace provided; using current directory. "
                "Files may be written to the bridge server directory.",
            )

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError as e:
            return ToolResult(
                name=tool_name,
                success=False,
                error=str(e),
            )

        augmented = dict(arguments)
        augmented["workspace"] = self._workspace

        permission_error = self._check_permissions(tool_name, augmented)
        if permission_error is not None:
            return permission_error

        logger.info(
            "tool_workspace_selected",
            workspace=self._workspace,
            tool=tool_name,
        )

        logger.info(TOOL_CALLED, tool=tool_name, args=sanitize_for_log(augmented))

        try:
            result = await tool.run(augmented)
        except Exception as e:
            logger.error(TOOL_COMPLETED, tool=tool_name, success=False, error=str(e))
            return ToolResult(
                name=tool_name,
                success=False,
                error=f"Tool execution failed: {e}",
            )

        logger.info(
            TOOL_COMPLETED,
            tool=tool_name,
            success=result.success,
            output_size=len(result.output),
        )

        return result

    def _check_permissions(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
        config = load_tool_permissions().get(tool_name, {})
        if not isinstance(config, dict):
            return None

        if config.get("enabled") is False:
            return ToolResult(name=tool_name, success=False, error=f"Tool {tool_name!r} is disabled by policy")

        path_error = self._check_path_policy(tool_name, arguments, config)
        if path_error is not None:
            return path_error

        size_error = self._check_size_policy(tool_name, arguments, config)
        if size_error is not None:
            return size_error

        timeout = config.get("timeout_seconds")
        if timeout is not None and "timeout" in arguments:
            arguments["timeout"] = min(int(arguments["timeout"]), int(timeout))

        return None

    def _check_path_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        config: dict[str, Any],
    ) -> ToolResult | None:
        raw_path = arguments.get("path")
        if raw_path is None:
            return None

        requested = str(raw_path) or "."
        if requested.startswith("/"):
            return ToolResult(name=tool_name, success=False, error="Absolute paths are not allowed by policy")
        if ".." in Path(requested).parts:
            return ToolResult(name=tool_name, success=False, error="Path traversal is not allowed by policy")

        normalized = Path(requested).as_posix().lstrip("./") or "."
        allow_paths = [str(path) for path in config.get("allow_paths", [])]
        deny_paths = [str(path) for path in config.get("deny_paths", [])]

        if allow_paths and not any(self._path_matches(normalized, allowed) for allowed in allow_paths):
            return ToolResult(
                name=tool_name,
                success=False,
                error=f"Path {requested!r} is not allowed by policy",
            )

        if any(self._path_matches(normalized, denied) for denied in deny_paths):
            return ToolResult(
                name=tool_name,
                success=False,
                error=f"Path {requested!r} is denied by policy",
            )

        return None

    def _check_size_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        config: dict[str, Any],
    ) -> ToolResult | None:
        max_size = config.get("max_size_bytes")
        if max_size is None:
            return None

        if "max_bytes" in arguments:
            arguments["max_bytes"] = min(int(arguments["max_bytes"]), int(max_size))

        content = arguments.get("content")
        if content is not None and len(str(content).encode("utf-8")) > int(max_size):
            return ToolResult(
                name=tool_name,
                success=False,
                error=f"Content exceeds max_size_bytes policy limit of {max_size}",
            )

        return None

    @staticmethod
    def _path_matches(path: str, pattern: str) -> bool:
        normalized_pattern = Path(pattern).as_posix().lstrip("./") or "."
        if normalized_pattern == ".":
            return True
        return fnmatch.fnmatch(path, normalized_pattern) or fnmatch.fnmatch(path, f"**/{normalized_pattern}")
