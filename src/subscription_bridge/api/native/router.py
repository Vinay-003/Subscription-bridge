from __future__ import annotations

from fastapi import APIRouter, Request

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.models import RunRequest, RunResponse
from subscription_bridge.api.native.service import run_agent

router = APIRouter()


def _get_deps(request: Request) -> AppDependencies:
    deps: AppDependencies = request.app.state.deps
    return deps


@router.post("/agent/runs", response_model=RunResponse)
async def create_agent_run(req: RunRequest, request: Request) -> RunResponse:
    return await run_agent(req, _get_deps(request))
