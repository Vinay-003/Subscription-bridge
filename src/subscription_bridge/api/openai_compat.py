from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, StreamingResponse

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.openai_models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceDelta,
    DeltaMessage,
    ModelList,
    OpenAIModel,
    ResponseMessage,
    Usage,
)
from subscription_bridge.providers.base import ProviderRequest

router = APIRouter()
_workspace_locks: dict[str, asyncio.Lock] = {}
_workspace_locks_guard = asyncio.Lock()

MODEL_FAKE = "subscription-bridge-fake"
MODEL_GEMINI_FAST = "subscription-bridge-gemini-fast"
MODEL_GEMINI_THINKING = "subscription-bridge-gemini-thinking"
MODEL_GEMINI_PRO = "subscription-bridge-gemini-pro"

GEMINI_MODELS = {MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO}

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 32000,
    MODEL_GEMINI_FAST: 1_000_000,
    MODEL_GEMINI_THINKING: 192_000,
    MODEL_GEMINI_PRO: 1_000_000,
}

MODEL_OUTPUT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 8192,
    MODEL_GEMINI_FAST: 8192,
    MODEL_GEMINI_THINKING: 65536,
    MODEL_GEMINI_PRO: 65536,
}

TOOL_CALL_SYSTEM_PROMPT = (
    'You have access to tools. When you need to use a tool, '
    'respond with a JSON object: {{"tool_calls": [{{"id": "call_1", '
    '"type": "function", "function": {{"name": "tool_name", '
    '"arguments": {{"arg1": "value1"}}}}}}]}}\n\n'
    "Available tools:\n{tools_desc}\n\n"
    "If you do not need a tool, respond normally with plain text."
)


def _get_deps(request: Request) -> AppDependencies:
    deps: AppDependencies = request.app.state.deps
    return deps


def _build_models() -> list[OpenAIModel]:
    models = [OpenAIModel(id=MODEL_FAKE, owned_by="subscription-bridge")]
    if importlib.util.find_spec("subscription_bridge.providers.gemini"):
        for mid in [MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO]:
            models.append(OpenAIModel(id=mid, owned_by="subscription-bridge"))
    return models


def _error_json(
    message: str,
    code: str = "invalid_request_error",
    param: str | None = None,
    status_code: int = 404,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": code, "param": param, "code": code}},
    )


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _strip_provider_prefix(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id


def _check_context_limit(req: ChatCompletionRequest) -> JSONResponse | None:
    model = _strip_provider_prefix(req.model)
    if model not in MODEL_CONTEXT_LIMITS:
        return None
    context_limit = MODEL_CONTEXT_LIMITS[model]

    total_text = ""
    for msg in req.messages:
        if isinstance(msg.content, str):
            total_text += msg.content
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total_text += str(part.get("text", ""))
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                total_text += json.dumps(tc, default=str)

    estimated = _estimate_tokens(total_text)
    if estimated > context_limit:
        return _error_json(
            f"Context length exceeded: estimated {estimated} tokens exceeds limit of {context_limit} tokens "
            f"for model {req.model}. OpenCode compaction is recommended.",
            code="context_length_exceeded",
            status_code=400,
        )
    return None


def _gemini_model_variant(model_id: str) -> str:
    mapping = {
        MODEL_GEMINI_FAST: "Gemini 3 Flash",
        MODEL_GEMINI_THINKING: "Gemini 3 Deep Think",
        MODEL_GEMINI_PRO: "Gemini 3.1 Pro",
    }
    return mapping.get(_strip_provider_prefix(model_id), "Gemini 3 Flash")


def _with_model_hint(prompt: str, variant: str) -> str:
    header = f"[Model: {variant}]"
    if not prompt:
        return header
    return f"{header}\n{prompt}"


def _resolve_agent_answer(result: Any) -> str:
    if result.answer:
        return result.answer
    if result.needs_clarification and result.question:
        return result.question
    if result.error:
        return f"Error: {result.error}"
    return "No answer generated"


def _conversation_id(messages: list[Any]) -> str:
    import hashlib
    raw = "|".join(
        str(m.role) + ":" + (str(m.content)[:200] if m.content else "")
        for m in messages[:6]
    )
    return "conv-" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _normalize_workspace(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        resolved = os.path.expanduser(value)
        resolved = os.path.abspath(resolved)
    except Exception:
        return None
    if os.path.isdir(resolved):
        return resolved
    return None


def _workspace_from_messages(messages: list[Any]) -> str | None:
    import re

    patterns = [
        r"workspace\s*[:=]\s*`?(/[^\s`]+)`?",
        r"project\s*(?:root|dir|directory)?\s*[:=]\s*`?(/[^\s`]+)`?",
        r"working\s*directory\s*[:=]\s*`?(/[^\s`]+)`?",
        r"cwd\s*[:=]\s*`?(/[^\s`]+)`?",
    ]
    for msg in messages:
        if not isinstance(msg.content, str):
            continue
        text = msg.content
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                candidate = candidate.rstrip(".,;:>)\"]}'")
                normalized = _normalize_workspace(candidate)
                if normalized:
                    return normalized
    return None


def _workspace_from_opencode_db(model_id: str | None = None) -> str | None:
    import sqlite3

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
        if model_id:
            cursor.execute(
                "select m.data, s.directory from message m "
                "join session s on s.id = m.session_id "
                "where m.data like ? "
                "and m.data like ? "
                "and s.directory is not null and s.directory != '' "
                "and (s.time_archived is null or s.time_archived = 0) "
                "order by m.time_updated desc limit 50",
                (
                    '%"providerID":"subscription-bridge"%',
                    f'%"modelID":"{_strip_provider_prefix(model_id)}"%',
                ),
            )
            rows = cursor.fetchall()
            for row in rows:
                if not row:
                    continue
                msg_data = row[0] if len(row) > 0 else None
                session_dir = row[1] if len(row) > 1 else None
                try:
                    parsed = json.loads(msg_data) if isinstance(msg_data, str) else {}
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict):
                    path_obj = parsed.get("path")
                    if isinstance(path_obj, dict):
                        cwd = path_obj.get("cwd")
                        normalized = _normalize_workspace(str(cwd) if cwd else None)
                        if normalized:
                            return normalized
                normalized_session_dir = _normalize_workspace(str(session_dir) if session_dir else None)
                if normalized_session_dir:
                    return normalized_session_dir

        cursor.execute(
            "select s.directory from session s "
            "where s.directory is not null and s.directory != '' "
            "and (s.time_archived is null or s.time_archived = 0) "
            "order by s.time_updated desc limit 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            normalized = _normalize_workspace(str(row[0]))
            if normalized:
                return normalized
        cursor.execute(
            "select worktree from project where worktree is not null "
            "and worktree != '' order by time_updated desc limit 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            normalized = _normalize_workspace(str(row[0]))
            if normalized:
                return normalized
        return None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _resolve_workspace(req: ChatCompletionRequest, request: Request) -> tuple[str, str]:
    headers = [
        ("x-workspace-root", request.headers.get("x-workspace-root")),
        ("x-workspace", request.headers.get("x-workspace")),
        ("x-opencode-workspace", request.headers.get("x-opencode-workspace")),
        ("x-opencode-project", request.headers.get("x-opencode-project")),
    ]
    for name, raw in headers:
        normalized = _normalize_workspace(raw)
        if normalized:
            return normalized, name

    normalized = _normalize_workspace(req.workspace)
    if normalized:
        return normalized, "body"

    from_messages = _workspace_from_messages(req.messages)
    if from_messages:
        return from_messages, "messages"

    from_opencode = _workspace_from_opencode_db(req.model)
    if from_opencode:
        return from_opencode, "opencode_db"

    return os.path.abspath("."), "default"


def _resolve_mode(request: Request) -> str:
    mode_header = request.headers.get("x-opencode-mode", "").lower()
    if mode_header in ["plan", "act"]:
        return mode_header
    return "act"


def _is_title_generator_request(req: ChatCompletionRequest) -> bool:
    for msg in req.messages:
        if msg.role != "system" or not isinstance(msg.content, str):
            continue
        content = msg.content.lower()
        if "you are a title generator" in content:
            return True
    return False


def _title_from_messages(messages: list[Any]) -> str:
    last_user = "Conversation"
    for msg in reversed(messages):
        if msg.role == "user" and isinstance(msg.content, str) and msg.content.strip():
            last_user = msg.content.strip()
            break
    cleaned = " ".join(last_user.split())
    if not cleaned:
        return "Conversation"
    words = cleaned.split(" ")
    title = " ".join(words[:6])
    if len(title) > 50:
        title = title[:50].rstrip()
    return title


async def _get_workspace_lock(workspace: str) -> asyncio.Lock:
    async with _workspace_locks_guard:
        lock = _workspace_locks.get(workspace)
        if lock is None:
            lock = asyncio.Lock()
            _workspace_locks[workspace] = lock
        return lock


async def _resolve_adapter(model_id: str, deps: AppDependencies) -> Any | None:
    model = _strip_provider_prefix(model_id)
    if model == MODEL_FAKE:
        return deps.get_registry().get("fake")
    if model in GEMINI_MODELS:
        try:
            return await deps.get_gemini_adapter()
        except Exception:
            return None
    return None


@router.get("/v1/models")
async def list_models(request: Request) -> ModelList:
    import structlog
    structlog.get_logger("bridge.api").info("list_models_requested")
    return ModelList(data=_build_models())


@router.get("/.well-known/opencode.json")
async def opencode_well_known() -> JSONResponse:
    return JSONResponse({
        "id": "subscription-bridge",
        "name": "SubscriptionBridge Local",
        "npm": "@ai-sdk/openai-compatible",
        "options": {
            "baseURL": "http://127.0.0.1:8787/v1",
        },
    })


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: dict[str, Any]) -> Any:
    import structlog
    log = structlog.get_logger("bridge.api")

    import json as _json
    log.info(
        "chat_completions_request",
        model=body.get("model"),
        msg_count=len(body.get("messages", [])),
        has_tools=bool(body.get("tools")),
        workspace_body=body.get("workspace"),
        workspace_header=request.headers.get("x-workspace-root") or request.headers.get("x-workspace"),
        body_preview=_json.dumps(body)[:500],
    )

    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        log.warning("chat_completions_parse_error", error=str(e))
        return _error_json(str(e), code="invalid_request_error", status_code=422)

    ctx_error = _check_context_limit(req)
    if ctx_error is not None:
        return ctx_error

    deps = _get_deps(request)

    if _is_title_generator_request(req):
        title = _title_from_messages(req.messages)
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}", created=int(time.time()), model=req.model,
            choices=[Choice(index=0, message=ResponseMessage(role="assistant", content=title), finish_reason="stop")],
            usage=Usage(
                prompt_tokens=_estimate_tokens(title),
                completion_tokens=_estimate_tokens(title),
                total_tokens=_estimate_tokens(title) * 2,
            ),
        )

    provider_adapter = await _resolve_adapter(req.model, deps)
    if provider_adapter is None:
        return _error_json(
            f"Model not found: {req.model}",
            code="model_not_found",
            param="model",
        )

    has_tools = bool(req.tools)
    prompt, system_prompt = _convert_messages(
        req.messages, req.tools,
        tool_choice=req.tool_choice,
        require_json_tools=has_tools,
    )

    resolved_workspace, workspace_source = _resolve_workspace(req, request)
    log.info("workspace_resolved", workspace=resolved_workspace, source=workspace_source)

    if _strip_provider_prefix(req.model) in GEMINI_MODELS:
        variant = _gemini_model_variant(req.model)
        prompt = _with_model_hint(prompt, variant)

    attachments: list[str] = []
    for msg in req.messages:
        if isinstance(msg.content, list):
            attachments.extend(_extract_images_from_content(msg.content))

    provider_req = ProviderRequest(
        run_id=_conversation_id(req.messages) if not has_tools else f"api-v1-{uuid.uuid4().hex[:8]}",
        prompt=prompt,
        system_prompt=system_prompt or None,
        attachments=attachments or None,
        require_json=has_tools,
        timeout_seconds=max(req.max_tokens // 100, 30),
        metadata={
            "gemini_model_variant": _gemini_model_variant(req.model)
            if _strip_provider_prefix(req.model) in GEMINI_MODELS
            else None,
        },
    )

    if req.stream and provider_adapter is not None and provider_adapter.name != "gemini":
        return StreamingResponse(
            _stream_response(provider_adapter, provider_req, req.model),
            media_type="text/event-stream",
        )

    if provider_adapter is not None and provider_adapter.name == "gemini" and has_tools:
        from subscription_bridge.core import AgentRuntime, Task
        from subscription_bridge.core.plan import AgentMode

        dep_tool_registry = deps.get_tool_registry()
        runtime = AgentRuntime(
            provider=provider_adapter,
            tool_registry=dep_tool_registry,
            max_steps=25,
        )
        last_text = ""
        for msg in reversed(req.messages):
            if isinstance(msg.content, str):
                last_text = msg.content
                break
            if isinstance(msg.content, list):
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        last_text = part.get("text", "") or ""
                        break
                if last_text:
                    break
        task_text = last_text or prompt
        variant = _gemini_model_variant(req.model)
        if variant:
            task_text = _with_model_hint(task_text, variant)

        mode_str = _resolve_mode(request)
        mode = AgentMode.PLAN if mode_str == "plan" else AgentMode.ACT

        task = Task(
            text=task_text,
            workspace=resolved_workspace,
            provider="gemini",
            max_steps=25,
            metadata={
                "gemini_model_variant": _gemini_model_variant(req.model)
                if _strip_provider_prefix(req.model) in GEMINI_MODELS
                else None,
            },
            mode=mode,
        )
        workspace_lock = await _get_workspace_lock(resolved_workspace)
        async with workspace_lock:
            result = await runtime.run(task)
        answer = _resolve_agent_answer(result)

        if req.stream:
            return StreamingResponse(
                _stream_agent_answer(answer, req.model),
                media_type="text/event-stream",
            )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}", created=int(time.time()), model=req.model,
            choices=[Choice(index=0, message=ResponseMessage(role="assistant", content=answer), finish_reason="stop")],
            usage=Usage(
                prompt_tokens=_estimate_tokens(prompt),
                completion_tokens=_estimate_tokens(answer),
                total_tokens=_estimate_tokens(prompt) + _estimate_tokens(answer),
            ),
        )

    # Non-Gemini providers (fake) use direct send_prompt
    response = await provider_adapter.send_prompt(provider_req)
    _cleanup_temp_files(attachments)

    if not response.success:
        return _error_json(response.error or "Provider error", code="provider_error", status_code=502)

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}", created=int(time.time()), model=req.model,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(content=response.text),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=_estimate_tokens(prompt),
            completion_tokens=_estimate_tokens(response.text),
            total_tokens=_estimate_tokens(prompt) + _estimate_tokens(response.text),
        ),
    )


def _convert_messages(
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    require_json_tools: bool = False,
) -> tuple[str, str]:
    system_parts: list[str] = []
    conversation: list[str] = []

    for msg in messages:
        role = msg.role
        content = msg.content
        text = _extract_text(content) if content else ""

        if role == "system":
            system_parts.append(text)
        elif role == "user":
            conversation.append(f"User: {text}")
        elif role == "assistant":
            if msg.tool_calls:
                for tc in (msg.tool_calls or []):
                    fn = tc.get("function", tc) if isinstance(tc, dict) else {}
                    name = fn.get("name", "?") if isinstance(fn, dict) else "?"
                    args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
                    conversation.append(f"Assistant (tool call): {name}({args})")
            if text:
                conversation.append(f"Assistant: {text}")
        elif role == "tool":
            name = ""
            if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                name = f" (call: {msg.tool_call_id})"
            conversation.append(f"Tool result{name}: {text[:1000]}")

    if tools and require_json_tools:
        import json as _json
        tools_desc_lines = []
        for t in tools:
            fname = t.get("function", t).get("name", "?") if isinstance(t, dict) else "?"
            fdesc = t.get("function", t).get("description", "") if isinstance(t, dict) else ""
            fparams = t.get("function", t).get("parameters", {}) if isinstance(t, dict) else {}
            tools_desc_lines.append(f"  {fname}: {fdesc} | args: {_json.dumps(fparams)[:300]}")
        tools_prompt = TOOL_CALL_SYSTEM_PROMPT.format(tools_desc="\n".join(tools_desc_lines))
        system_parts.append(tools_prompt)

    system_prompt = "\n".join(system_parts) if system_parts else ""

    parts: list[str] = []
    if conversation:
        parts.append("Conversation:")
        parts.extend(conversation)
        parts.append("")

    prompt = "\n".join(parts).strip()
    return prompt, system_prompt


def _extract_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
    return "\n".join(texts)


def _extract_images_from_content(content: str | list[dict[str, Any]]) -> list[str]:
    if isinstance(content, str):
        return []
    paths: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            url = part.get("image_url", {})
            if isinstance(url, dict):
                url = url.get("url", "")
            if not url:
                continue
            path = _save_image(url)
            if path:
                paths.append(path)
    return paths


def _save_image(url: str) -> str | None:
    try:
        if url.startswith("data:"):
            match = re.match(r"data:image/(\w+);base64,(.+)", url)
            if not match:
                return None
            ext = match.group(1)
            data = base64.b64decode(match.group(2))
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=f".{ext}", delete=False,
                prefix="bridge_img_",
            ) as f:
                f.write(data)
                return f.name
        else:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            ext = "png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = "jpg"
            elif "gif" in content_type:
                ext = "gif"
            elif "webp" in content_type:
                ext = "webp"
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=f".{ext}", delete=False,
                prefix="bridge_img_",
            ) as f:
                f.write(response.content)
                return f.name
    except Exception:
        return None


def _cleanup_temp_files(paths: list[str]) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    import json as _json
    text = text.strip()
    try:
        data = _json.loads(text)
        if isinstance(data, dict) and "tool_calls" in data:
            raw = data["tool_calls"]
            return list(raw) if isinstance(raw, list) else []
        if isinstance(data, list):
            return data
    except _json.JSONDecodeError:
        pass
    import re as _re
    m = _re.search(r'\{[^{}]*"tool_calls"[^{}]*\}', text, _re.DOTALL)
    if m:
        try:
            data = _json.loads(m.group(0))
            if isinstance(data, dict) and "tool_calls" in data:
                raw = data["tool_calls"]
                return list(raw) if isinstance(raw, list) else []
        except _json.JSONDecodeError:
            pass
    return []


async def _stream_response(
    adapter: Any,
    request: ProviderRequest,
    model: str,
) -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    role_chunk = ChatCompletionChunk(
        id=completion_id, created=now, model=model,
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(role="assistant"), finish_reason=None)],
    )
    yield f"data: {role_chunk.model_dump_json()}\n\n"

    response = await adapter.send_prompt(request)

    if response.success and response.text:
        text = response.text
        chunk_size = max(len(text) // 10, 5)
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i : i + chunk_size]
            content_chunk = ChatCompletionChunk(
                id=completion_id, created=now, model=model,
                choices=[ChoiceDelta(index=0, delta=DeltaMessage(content=chunk_text), finish_reason=None)],
            )
            yield f"data: {content_chunk.model_dump_json()}\n\n"
            await asyncio.sleep(0.01)

    stop_chunk = ChatCompletionChunk(
        id=completion_id, created=now, model=model,
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {stop_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


async def _stream_agent_answer(answer: str, model: str) -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    role_chunk = ChatCompletionChunk(
        id=completion_id, created=now, model=model,
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(role="assistant"), finish_reason=None)],
    )
    yield f"data: {role_chunk.model_dump_json()}\n\n"
    if answer:
        chunk_size = max(len(answer) // 10, 5)
        for i in range(0, len(answer), chunk_size):
            chunk_text = answer[i:i + chunk_size]
            content_chunk = ChatCompletionChunk(
                id=completion_id, created=now, model=model,
                choices=[ChoiceDelta(index=0, delta=DeltaMessage(content=chunk_text), finish_reason=None)],
            )
            yield f"data: {content_chunk.model_dump_json()}\n\n"
            await asyncio.sleep(0.01)
    stop_chunk = ChatCompletionChunk(
        id=completion_id, created=now, model=model,
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {stop_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    error_chunk = ChatCompletionChunk(
        id="error", created=int(time.time()), model="unknown",
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(content=f"Error: {message}"), finish_reason="stop")],
    )
    yield f"data: {error_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
