from __future__ import annotations

from fastapi import HTTPException

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.models import RunRequest, RunResponse
from subscription_bridge.core import AgentRuntime, Task
from subscription_bridge.providers.base import ProviderAdapter


async def run_agent(req: RunRequest, deps: AppDependencies) -> RunResponse:
    provider_adapter = await _resolve_provider(req.provider, deps)

    runtime = AgentRuntime(
        provider=provider_adapter,
        tool_registry=deps.get_tool_registry(),
        max_steps=req.max_steps,
    )

    task = Task(
        text=req.task,
        workspace=req.workspace,
        provider=req.provider,
        max_steps=req.max_steps,
    )

    result = await runtime.run(task)

    return RunResponse(
        success=result.success,
        answer=result.answer,
        run_id=result.run_id,
        steps=result.steps,
        status=result.summary.get("status", ""),
        error=result.error,
    )


async def _resolve_provider(provider: str, deps: AppDependencies) -> ProviderAdapter:
    if provider == "gemini":
        try:
            return await deps.get_gemini_adapter()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Gemini unavailable: {e}") from e

    if provider == "chatgpt":
        try:
            return await deps.get_chatgpt_adapter()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ChatGPT unavailable: {e}") from e

    registry = deps.get_registry()
    try:
        return registry.get(provider)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
