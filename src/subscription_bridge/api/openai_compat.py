from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, StreamingResponse

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.openai.message_converter import (
    cleanup_temp_files,
    convert_messages,
    extract_images_from_content,
    extract_text,
    save_image,
)
from subscription_bridge.api.openai.model_catalog import (
    CHATGPT_MODELS,
    GEMINI_MODELS,
    MODEL_FAKE,
    build_models,
    chatgpt_model_variant,
    context_limit_for_model,
    gemini_model_variant,
    is_chatgpt_model,
    is_gemini_model,
    resolve_model_alias,
    strip_provider_prefix,
)
from subscription_bridge.api.openai.streaming import error_stream, stream_agent_answer, stream_response
from subscription_bridge.api.openai.tool_parser import parse_tool_calls
from subscription_bridge.api.openai_models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ModelList,
    OpenAIModel,
    ResponseMessage,
    ToolCall,
    Usage,
)
from subscription_bridge.providers.base import ProviderRequest
from subscription_bridge.workspace import resolve_workspace

router = APIRouter()

def _get_deps(request: Request) -> AppDependencies:
    deps: AppDependencies = request.app.state.deps
    return deps


def _build_models() -> list[OpenAIModel]:
    return build_models()


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
    return strip_provider_prefix(model_id)


def _resolve_model_alias(model_id: str) -> str:
    return resolve_model_alias(model_id)


def _check_context_limit(req: ChatCompletionRequest) -> JSONResponse | None:
    context_limit = context_limit_for_model(req.model)
    if context_limit is None:
        return None

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
    return gemini_model_variant(model_id)


def _chatgpt_model_variant(model_id: str) -> str:
    return chatgpt_model_variant(model_id)


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


async def _resolve_adapter(model_id: str, deps: AppDependencies) -> Any | None:
    model = _strip_provider_prefix(model_id)
    if model == MODEL_FAKE:
        return deps.get_registry().get("fake")
    if model in GEMINI_MODELS:
        try:
            return await deps.get_gemini_adapter()
        except Exception:
            return None
    if model in CHATGPT_MODELS:
        try:
            return await deps.get_chatgpt_adapter()
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

    req.model = _resolve_model_alias(req.model)
    log.info("model_resolved", original=body.get("model"), resolved=req.model)

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

    workspace_resolution = resolve_workspace(req, request)
    log.info("workspace_resolved", workspace=workspace_resolution.path, source=workspace_resolution.source)

    if is_gemini_model(req.model):
        variant = _gemini_model_variant(req.model)
        prompt = _with_model_hint(prompt, variant)
    elif is_chatgpt_model(req.model):
        variant = _chatgpt_model_variant(req.model)
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
            if is_gemini_model(req.model)
            else None,
            "chatgpt_model_variant": _chatgpt_model_variant(req.model)
            if is_chatgpt_model(req.model)
            else None,
        },
    )

    if req.stream and provider_adapter is not None and provider_adapter.name == "fake":
        return StreamingResponse(
            _stream_response(provider_adapter, provider_req, req.model),
            media_type="text/event-stream",
        )

    # OpenAI compatibility mode is a model gateway. It may return tool_calls,
    # but it never executes local tools; clients such as OpenCode own execution.
    response = await provider_adapter.send_prompt(provider_req)
    _cleanup_temp_files(attachments)

    if not response.success:
        return _error_json(response.error or "Provider error", code="provider_error", status_code=502)

    parsed_tool_calls = _parse_tool_calls(response.text) if has_tools else []
    if parsed_tool_calls:
        for idx, tool_call in enumerate(parsed_tool_calls, start=1):
            if not tool_call.id:
                tool_call.id = f"call_{idx}"
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}", created=int(time.time()), model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=ResponseMessage(role="assistant", content=None, tool_calls=parsed_tool_calls),
                    finish_reason="tool_calls",
                )
            ],
            usage=Usage(
                prompt_tokens=_estimate_tokens(prompt),
                completion_tokens=_estimate_tokens(response.text),
                total_tokens=_estimate_tokens(prompt) + _estimate_tokens(response.text),
            ),
        )

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
    return convert_messages(messages, tools, tool_choice, require_json_tools)


def _extract_text(content: str | list[dict[str, Any]]) -> str:
    return extract_text(content)


def _extract_images_from_content(content: str | list[dict[str, Any]]) -> list[str]:
    return extract_images_from_content(content)


def _save_image(url: str) -> str | None:
    return save_image(url)


def _cleanup_temp_files(paths: list[str]) -> None:
    cleanup_temp_files(paths)


def _parse_tool_calls(text: str) -> list[ToolCall]:
    return parse_tool_calls(text)


async def _stream_response(
    adapter: Any,
    request: ProviderRequest,
    model: str,
) -> AsyncGenerator[str, None]:
    async for chunk in stream_response(adapter, request, model):
        yield chunk


async def _stream_agent_answer(answer: str, model: str) -> AsyncGenerator[str, None]:
    async for chunk in stream_agent_answer(answer, model):
        yield chunk


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    async for chunk in error_stream(message):
        yield chunk
