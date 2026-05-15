from __future__ import annotations

import re
from typing import Any

from subscription_bridge.core.agent_state import AgentState
from subscription_bridge.core.loop_controller import LoopController
from subscription_bridge.core.planner import Planner
from subscription_bridge.core.run_manager import RunResult
from subscription_bridge.core.task import Task
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.providers.base import ProviderAdapter
from subscription_bridge.tools.executor import ToolExecutor
from subscription_bridge.tools.registry import ToolRegistry

logger = get_logger(__name__)

_FILE_PATTERN = re.compile(r'(?<![.\w])[\w.\-/]+\.[a-zA-Z]{1,4}(?![.\w])')
_SKIP_PATTERNS = re.compile(
    r'^(json\.loads|json\.dumps|re\.\w+|os\.\w+|sys\.\w+|'
    r'pathlib\.|typing\.|__init__|__name__|__main__|__file__)$',
    re.IGNORECASE,
)


def _find_file_refs(text: str) -> list[str]:
    matches = _FILE_PATTERN.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        lower = m.lower()
        if lower in seen:
            continue
        seen.add(lower)
        if _SKIP_PATTERNS.match(m):
            continue
        result.append(m)
    return result


async def _auto_read_files(task_text: str, tool_executor: ToolExecutor) -> list[dict[str, Any]]:
    refs = _find_file_refs(task_text)
    if not refs:
        return []

    auto_results: list[dict[str, Any]] = []
    for ref in refs:
        for fpath in (ref,):
            fr = await tool_executor.execute("file_read", {"path": fpath})
            if fr.success:
                auto_results.append({
                    "tool_name": "file_read",
                    "arguments": {"path": fpath},
                    "result": fr.output[:5000],
                    "success": True,
                })
                logger.info("auto_read_file", path=fpath, size=len(fr.output[:5000]))
    return auto_results


class AgentRuntime:
    def __init__(
        self,
        provider: ProviderAdapter,
        tool_registry: ToolRegistry | None = None,
        max_steps: int = 10,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry or ToolRegistry()
        self._max_steps = max_steps

    async def run(self, task: Task) -> RunResult:
        state = AgentState(
            task=task.text,
            workspace=task.workspace,
        )
        state.max_steps = task.max_steps or self._max_steps

        tool_executor = ToolExecutor(self._tool_registry, workspace=task.workspace)

        auto_reads = await _auto_read_files(task.text, tool_executor)
        auto_context: list[str] = []
        for ar in auto_reads:
            path = ar["arguments"].get("path", "?")
            preview = (ar["result"] or "")[:2000]
            auto_context.append(
                f"[Auto-read file: {path}]\n{preview}\n"
            )
        if auto_context:
            state.auto_file_context = "\n".join(auto_context)
            logger.info("auto_read_context", files=len(auto_reads))

        planner = Planner(self._tool_registry.describe_tools_for_prompt())
        controller = LoopController(
            provider=self._provider,
            tool_executor=tool_executor,
            planner=planner,
            max_steps=state.max_steps,
            metadata=task.metadata,
        )

        result = await controller.run(state)

        result.run_id = state.run_id
        return result
