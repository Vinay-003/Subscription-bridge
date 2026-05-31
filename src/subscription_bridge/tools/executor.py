from __future__ import annotations

import os
from typing import Any

from subscription_bridge.core.errors import ToolNotFoundError
from subscription_bridge.logging.events import TOOL_CALLED, TOOL_COMPLETED
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.tools.base import ToolResult
from subscription_bridge.tools.registry import ToolRegistry
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
