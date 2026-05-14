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


def _conversation_id(messages: list[Any]) -> str:
    import hashlib
    raw = "|".join(
        str(m.role) + ":" + (str(m.content)[:200] if m.content else "")
        for m in messages[:6]
    )
    return "conv-" + hashlib.md5(raw.encode()).hexdigest()[:12]


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
    log.info("chat_completions_request",
             model=body.get("model"),
             msg_count=len(body.get("messages", [])),
             has_tools=bool(body.get("tools")),
             body_preview=_json.dumps(body)[:500])

    try:
        req = ChatCompletionRequest(**body)
    except Exception as e:
        log.warning("chat_completions_parse_error", error=str(e))
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

    if _strip_provider_prefix(req.model) in GEMINI_MODELS:
        variant = _gemini_model_variant(req.model)
        if not has_tools:
            model_hint = f"\n\n[Using {variant} — continue in the existing Gemini chat tab]"
            prompt += model_hint

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
    )

    if req.stream and provider_adapter is not None and provider_adapter.name != "gemini":
        return StreamingResponse(
            _stream_response(provider_adapter, provider_req, req.model),
            media_type="text/event-stream",
        )

    if provider_adapter is not None and provider_adapter.name == "gemini" and has_tools:
        from subscription_bridge.core import AgentRuntime, Task

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
            task_text = f"[Model: {variant}]\n{task_text}"
        task = Task(text=task_text, workspace=".", provider="gemini", max_steps=25)
        result = await runtime.run(task)
        answer = result.answer or "No answer generated"

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
