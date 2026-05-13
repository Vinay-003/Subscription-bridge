from __future__ import annotations

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
        planner = Planner(self._tool_registry.describe_tools_for_prompt())
        controller = LoopController(
            provider=self._provider,
            tool_executor=tool_executor,
            planner=planner,
            max_steps=state.max_steps,
        )

        result = await controller.run(state)

        result.run_id = state.run_id
        return result
