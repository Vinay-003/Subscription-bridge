from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = ""
    providers: dict[str, str] = {}
    models: list[str] = []
    tool_count: int = 0
    native_agent: bool = True


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    provider: str = "fake"
    files: list[str] = []
    timeout_seconds: int = 300


class AskResponse(BaseModel):
    success: bool
    provider: str = ""
    text: str = ""
    error: str | None = None
    artifacts: list[str] = []
    metadata: dict[str, Any] = {}


class RunRequest(BaseModel):
    task: str = Field(..., min_length=1)
    provider: str = "fake"
    workspace: str = "."
    max_steps: int = 10


class RunResponse(BaseModel):
    success: bool
    answer: str = ""
    run_id: str = ""
    steps: int = 0
    status: str = ""
    error: str | None = None


class SessionInfo(BaseModel):
    session_id: str = ""
    provider_name: str = ""
    state: str = ""
    current_run_id: str | None = None
    created_at: float = 0.0
    last_used_at: float = 0.0
    age_seconds: float = 0.0
    idle_seconds: float = 0.0


class SessionsResponse(BaseModel):
    sessions: list[SessionInfo] = []


class CodebaseIndexRequest(BaseModel):
    workspace: str = "."


class CodebaseIndexResponse(BaseModel):
    success: bool
    file_count: int = 0
    chunk_count: int = 0
    symbol_count: int = 0
    duration_seconds: float = 0.0
    index_path: str = ""
    error: str | None = None


class CodebaseSearchRequest(BaseModel):
    workspace: str = "."
    query: str = ""
    top_k: int = 10


class SearchResultItem(BaseModel):
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    score: float = 0.0
    match_type: str = ""
    preview: str = ""
    symbols: list[str] = []


class CodebaseSearchResponse(BaseModel):
    success: bool
    results: list[SearchResultItem] = []
    indexed: bool = False
    error: str | None = None


class CodebaseStatsResponse(BaseModel):
    success: bool
    workspace_root: str = ""
    indexed_at: float = 0.0
    file_count: int = 0
    chunk_count: int = 0
    symbol_count: int = 0
    embedding_provider: str = ""
    embedding_dim: int = 0
    index_path: str = ""
    error: str | None = None


class ErrorResponse(BaseModel):
    detail: str
    error_type: str = ""
