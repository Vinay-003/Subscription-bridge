from __future__ import annotations

import time as _time

from fastapi import APIRouter, HTTPException, Request

from subscription_bridge import __version__
from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.models import (
    AskRequest,
    AskResponse,
    CodebaseIndexRequest,
    CodebaseIndexResponse,
    CodebaseSearchRequest,
    CodebaseSearchResponse,
    CodebaseStatsResponse,
    HealthResponse,
    RunRequest,
    RunResponse,
    SearchResultItem,
    SessionInfo,
    SessionsResponse,
)
from subscription_bridge.core import AgentRuntime, Task
from subscription_bridge.memory.codebase_indexer import CodebaseIndexer
from subscription_bridge.memory.retriever import Retriever
from subscription_bridge.providers.base import ProviderRequest

router = APIRouter()


def _get_deps(request: Request) -> AppDependencies:
    deps: AppDependencies = request.app.state.deps
    return deps


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    deps = _get_deps(request)
    providers = await deps.get_provider_healths()
    return HealthResponse(
        status="ok",
        version=__version__,
        providers=providers,
    )


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request) -> AskResponse:
    deps = _get_deps(request)
    from subscription_bridge.providers.base import ProviderAdapter

    provider_adapter: ProviderAdapter

    if req.provider == "gemini":
        try:
            gemini_ap = await deps.get_gemini_adapter()
            provider_adapter = gemini_ap
        except Exception as e:
            return AskResponse(success=False, error=f"Gemini unavailable: {e}")
    else:
        registry = deps.get_registry()
        try:
            provider_adapter = registry.get(req.provider)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    provider_req = ProviderRequest(
        run_id="api-ask",
        prompt=req.prompt,
        attachments=req.files if req.files else None,
        timeout_seconds=req.timeout_seconds,
    )

    response = await provider_adapter.send_prompt(provider_req)

    return AskResponse(
        success=response.success,
        provider=response.provider,
        text=response.text,
        error=response.error,
        artifacts=response.artifacts,
        metadata=dict(response.metadata),
    )


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest, request: Request) -> RunResponse:
    deps = _get_deps(request)
    from subscription_bridge.providers.base import ProviderAdapter

    provider_adapter: ProviderAdapter

    if req.provider == "gemini":
        try:
            gemini_ap = await deps.get_gemini_adapter()
            provider_adapter = gemini_ap
        except Exception as e:
            return RunResponse(success=False, error=f"Gemini unavailable: {e}")
    else:
        registry = deps.get_registry()
        try:
            provider_adapter = registry.get(req.provider)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    tool_registry = deps.get_tool_registry()
    runtime = AgentRuntime(
        provider=provider_adapter,
        tool_registry=tool_registry,
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


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(request: Request) -> SessionsResponse:
    deps = _get_deps(request)
    pool = deps.get_session_pool()
    if pool is None:
        return SessionsResponse(sessions=[])

    raw = pool.list_sessions()
    sessions = [
        SessionInfo(
            session_id=s["session_id"],
            provider_name=s["provider_name"],
            state=s["state"],
            current_run_id=s.get("current_run_id"),
            created_at=s.get("created_at", 0.0),
            last_used_at=s.get("last_used_at", 0.0),
            age_seconds=s.get("age_seconds", 0.0),
            idle_seconds=s.get("idle_seconds", 0.0),
        )
        for s in raw
    ]
    return SessionsResponse(sessions=sessions)


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str, request: Request) -> dict[str, str]:
    deps = _get_deps(request)
    pool = deps.get_session_pool()
    if pool is None:
        raise HTTPException(status_code=404, detail="No session pool available")

    session = pool.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    await pool.reset(session_id)
    return {"status": "reset", "session_id": session_id}


@router.post("/codebase/index", response_model=CodebaseIndexResponse)
async def codebase_index(req: CodebaseIndexRequest, request: Request) -> CodebaseIndexResponse:
    try:
        indexer = CodebaseIndexer(workspace=req.workspace)
        start = _time.monotonic()
        data = indexer.index()
        elapsed = _time.monotonic() - start

        return CodebaseIndexResponse(
            success=True,
            file_count=data.metadata.file_count,
            chunk_count=data.metadata.chunk_count,
            symbol_count=len(data.symbols),
            duration_seconds=round(elapsed, 2),
            index_path=str(indexer.index_dir),
        )
    except Exception as e:
        return CodebaseIndexResponse(success=False, error=str(e))


@router.post("/codebase/search", response_model=CodebaseSearchResponse)
async def codebase_search(req: CodebaseSearchRequest, request: Request) -> CodebaseSearchResponse:
    try:
        indexer = CodebaseIndexer(workspace=req.workspace)
        index_data = indexer.load_existing()

        if index_data is None:
            return CodebaseSearchResponse(
                success=True,
                indexed=False,
                error="No codebase index found. Run /codebase/index first.",
            )

        retriever = Retriever()
        results = retriever.retrieve(req.query, index_data, top_k=req.top_k)

        items = [
            SearchResultItem(
                file_path=r.file_path,
                start_line=r.start_line,
                end_line=r.end_line,
                score=r.score,
                match_type=r.match_type,
                preview=r.preview[:200] if r.preview else "",
                symbols=r.symbols,
            )
            for r in results
        ]

        return CodebaseSearchResponse(success=True, results=items, indexed=True)
    except Exception as e:
        return CodebaseSearchResponse(success=False, error=str(e))


@router.get("/codebase/stats", response_model=CodebaseStatsResponse)
async def codebase_stats(request: Request, workspace: str = ".") -> CodebaseStatsResponse:
    try:
        indexer = CodebaseIndexer(workspace=workspace)
        index_data = indexer.load_existing()

        if index_data is None:
            return CodebaseStatsResponse(
                success=False,
                error="No codebase index found. Run /codebase/index first.",
            )

        return CodebaseStatsResponse(
            success=True,
            workspace_root=index_data.metadata.workspace_root,
            indexed_at=index_data.metadata.indexed_at,
            file_count=index_data.metadata.file_count,
            chunk_count=index_data.metadata.chunk_count,
            symbol_count=len(index_data.symbols),
            embedding_provider=index_data.metadata.embedding_provider,
            embedding_dim=index_data.metadata.embedding_dim,
            index_path=str(indexer.index_dir),
        )
    except Exception as e:
        return CodebaseStatsResponse(success=False, error=str(e))
