from __future__ import annotations

import os
import sqlite3
import subprocess
from typing import Any

from subscription_bridge.core.errors import ToolNotFoundError
from subscription_bridge.logging.events import TOOL_CALLED, TOOL_COMPLETED
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.tools.base import ToolResult
from subscription_bridge.tools.registry import ToolRegistry
from subscription_bridge.utils.security import sanitize_for_log

logger = get_logger(__name__)


def _workspace_from_opencode_active_session() -> str | None:
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    db_path = os.environ.get("OPENCODE_DB_PATH", os.path.join(data_home, "opencode", "opencode.db"))
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=0.2)
    except Exception:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "select s.directory from session s "
            "where s.directory is not null and s.directory != '' "
            "and (s.time_archived is null or s.time_archived = 0) "
            "order by s.time_updated desc limit 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            candidate = os.path.abspath(os.path.expanduser(str(row[0])))
            if os.path.isdir(candidate):
                return candidate
        return None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _workspace_from_pwd(candidate_workspace: str | None) -> str | None:
    if not candidate_workspace:
        return None
    if not os.path.isdir(candidate_workspace):
        return None
    try:
        proc = subprocess.run(
            ["bash", "-lc", "pwd"],
            cwd=candidate_workspace,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    resolved = (proc.stdout or "").strip()
    if not resolved:
        return None
    resolved = os.path.abspath(os.path.expanduser(resolved))
    if os.path.isdir(resolved):
        return resolved
    return None


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, workspace: str = ".") -> None:
        self._registry = registry
        self._workspace = workspace

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
        if "workspace" not in augmented:
            base_workspace = self._workspace
            if base_workspace and os.path.isdir(base_workspace):
                augmented["workspace"] = base_workspace
            else:
                dynamic_workspace = _workspace_from_opencode_active_session()
                if dynamic_workspace:
                    augmented["workspace"] = dynamic_workspace
                    logger.info("tool_workspace_refreshed", old_workspace=self._workspace, workspace=dynamic_workspace)
                else:
                    augmented["workspace"] = self._workspace

        verified_workspace = _workspace_from_pwd(augmented.get("workspace"))
        if verified_workspace:
            if verified_workspace != augmented.get("workspace"):
                logger.info(
                    "tool_workspace_verified",
                    original_workspace=augmented.get("workspace"),
                    verified_workspace=verified_workspace,
                )
            augmented["workspace"] = verified_workspace

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
