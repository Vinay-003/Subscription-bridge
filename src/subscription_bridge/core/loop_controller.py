from __future__ import annotations

from subscription_bridge.core.agent_state import AgentState
from subscription_bridge.core.errors import ProviderResponseError
from subscription_bridge.core.planner import Planner
from subscription_bridge.core.run_manager import RunResult
from subscription_bridge.logging.events import (
    PROMPT_SENT,
    RESPONSE_RECEIVED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    TOOL_CALLED,
    TOOL_COMPLETED,
)
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.parsing.json_parser import parse_agent_action
from subscription_bridge.parsing.schemas import AgentAction
from subscription_bridge.providers.base import ProviderAdapter, ProviderRequest
from subscription_bridge.tools.executor import ToolExecutor
from subscription_bridge.utils.security import sanitize_for_log

logger = get_logger(__name__)


class LoopController:
    def __init__(
        self,
        provider: ProviderAdapter,
        tool_executor: ToolExecutor,
        planner: Planner,
        max_steps: int = 10,
    ) -> None:
        self._provider = provider
        self._tool_executor = tool_executor
        self._planner = planner
        self._max_steps = max_steps

    async def run(self, state: AgentState) -> RunResult:
        state.start()
        state.max_steps = self._max_steps
        logger.info(RUN_STARTED, run_id=state.run_id, task=state.task)

        try:
            for step in range(1, self._max_steps + 1):
                action, tool_result = await self._execute_step(state, step)

                if action.action_type == "final":
                    state.complete(action.answer)
                    logger.info(
                        RUN_COMPLETED,
                        run_id=state.run_id,
                        steps=step,
                        answer_preview=action.answer[:100],
                    )
                    return RunResult(
                        success=True,
                        answer=action.answer,
                        run_id=state.run_id,
                        steps=step,
                        max_steps=self._max_steps,
                        total_elapsed=state.summary["elapsed_seconds"],
                        summary=state.summary,
                    )

                if action.action_type == "ask_clarification":
                    state.request_clarification(action.question)
                    return RunResult(
                        success=False,
                        needs_clarification=True,
                        question=action.question,
                        run_id=state.run_id,
                        steps=step,
                        max_steps=self._max_steps,
                        total_elapsed=state.summary["elapsed_seconds"],
                        summary=state.summary,
                    )

            state.exceed_max_steps()
            return RunResult(
                success=False,
                error=f"Max steps ({self._max_steps}) exceeded",
                run_id=state.run_id,
                steps=self._max_steps,
                max_steps=self._max_steps,
                total_elapsed=state.summary["elapsed_seconds"],
                summary=state.summary,
            )

        except Exception as e:
            state.fail(str(e))
            logger.error(RUN_FAILED, run_id=state.run_id, error=str(e))
            return RunResult(
                success=False,
                error=str(e),
                run_id=state.run_id,
                steps=state.steps,
                max_steps=self._max_steps,
                total_elapsed=state.summary["elapsed_seconds"],
                summary=state.summary,
            )

    async def _execute_step(self, state: AgentState, step: int) -> tuple[AgentAction, str | None]:
        prompt = self._planner.build_prompt(state)

        logger.info(PROMPT_SENT, run_id=state.run_id, step=step, prompt_size=len(prompt))

        request = ProviderRequest(
            run_id=state.run_id,
            prompt=prompt,
            require_json=True,
        )
        provider_response = await self._provider.send_prompt(request)

        if not provider_response.success:
            msg = provider_response.error or "Provider returned no response"
            raise ProviderResponseError(self._provider.name, msg)

        logger.info(
            RESPONSE_RECEIVED,
            run_id=state.run_id,
            step=step,
            response_size=len(provider_response.text),
        )

        action = parse_agent_action(provider_response.text)

        if action.action_type == "tool_call":
            tool_result = await self._execute_tool(state, step, action)
            return action, tool_result

        return action, None

    async def _execute_tool(self, state: AgentState, step: int, action: AgentAction) -> str:
        logger.info(
            TOOL_CALLED,
            run_id=state.run_id,
            step=step,
            tool=action.tool_name,
            args=sanitize_for_log(action.arguments),
        )

        result = await self._tool_executor.execute(action.tool_name, action.arguments)

        safe_output = sanitize_for_log(result.output)
        logger.info(
            TOOL_COMPLETED,
            run_id=state.run_id,
            step=step,
            tool=action.tool_name,
            success=result.success,
            output_size=len(result.output),
        )

        state.add_observation(
            action={"tool_name": action.tool_name, "arguments": action.arguments},
            result=safe_output or "",
            success=result.success,
        )

        return safe_output or ""

    @property
    def max_steps(self) -> int:
        return self._max_steps
