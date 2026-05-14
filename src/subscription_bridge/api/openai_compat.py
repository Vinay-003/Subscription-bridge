from __future__ import annotations

import asyncio
import importlib
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

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
    ToolCall,
    Usage,
)
from subscription_bridge.providers.base import ProviderRequest

router = APIRouter()

MODEL_FAKE = "subscription-bridge-fake"
MODEL_GEMINI_FAST = "subscription-bridge-gemini-fast"
MODEL_GEMINI_THINKING = "subscription-bridge-gemini-thinking"
MODEL_GEMINI_PRO = "subscription-bridge-gemini-pro"

GEMINI_MODELS = {MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO}

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 32000,
    MODEL_GEMINI_FAST: 100000,
    MODEL_GEMINI_THINKING: 500000,
    MODEL_GEMINI_PRO: 900000,
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


def _check_context_limit(req: ChatCompletionRequest) -> JSONResponse | None:
    if req.model not in MODEL_CONTEXT_LIMITS:
        return None
    context_limit = MODEL_CONTEXT_LIMITS[req.model]

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
        MODEL_GEMINI_FAST: "2.0 Flash",
        MODEL_GEMINI_THINKING: "2.5 Pro (thinking)",
        MODEL_GEMINI_PRO: "2.5 Pro",
    }
    return mapping.get(model_id, "2.0 Flash")


async def _resolve_adapter(model_id: str, deps: AppDependencies) -> Any | None:
    if model_id == MODEL_FAKE:
        return deps.get_registry().get("fake")
    if model_id in GEMINI_MODELS:
        try:
            return await deps.get_gemini_adapter()
        except Exception:
            return None
    return None


@router.get("/v1/models")
async def list_models(request: Request) -> ModelList:
    return ModelList(data=_build_models())


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: dict[str, Any]) -> Any:
    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        return _error_json(str(e), code="invalid_request_error", status_code=422)

    ctx_error = _check_context_limit(req)
    if ctx_error is not None:
        return ctx_error

    deps = _get_deps(request)

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

    provider_req = ProviderRequest(
        run_id=f"api-v1-{uuid.uuid4().hex[:8]}",
        prompt=prompt,
        system_prompt=system_prompt or None,
        require_json=has_tools,
        timeout_seconds=max(req.max_tokens // 100, 30),
    )

    if req.stream:
        return StreamingResponse(
            _stream_response(provider_adapter, provider_req, req.model),
            media_type="text/event-stream",
        )

    response = await provider_adapter.send_prompt(provider_req)

    if not response.success:
        return _error_json(response.error or "Provider error", code="provider_error", status_code=502)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    if has_tools:
        parsed = _parse_tool_calls(response.text)
        if parsed:
            tc_choices = [
                Choice(
                    index=0,
                    message=ResponseMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[ToolCall(**tc) for tc in parsed],
                    ),
                    finish_reason="tool_calls",
                )
            ]
            return ChatCompletionResponse(
                id=completion_id, created=now, model=req.model,
                choices=tc_choices,
                usage=Usage(
                    prompt_tokens=_estimate_tokens(prompt),
                    completion_tokens=_estimate_tokens(response.text),
                    total_tokens=_estimate_tokens(prompt) + _estimate_tokens(response.text),
                ),
            )

    return ChatCompletionResponse(
        id=completion_id, created=now, model=req.model,
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


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    error_chunk = ChatCompletionChunk(
        id="error", created=int(time.time()), model="unknown",
        choices=[ChoiceDelta(index=0, delta=DeltaMessage(content=f"Error: {message}"), finish_reason="stop")],
    )
    yield f"data: {error_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
