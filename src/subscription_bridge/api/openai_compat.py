from __future__ import annotations

import hashlib
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
    compact_system_prompt,
    convert_messages,
    extract_images_from_content,
    extract_text,
    render_system_prompt,
    save_image,
)
from subscription_bridge.api.openai.model_catalog import (
    build_models,
    chatgpt_model_variant,
    context_limit_for_model,
    gemini_model_variant,
    resolve_model_alias,
    strip_provider_prefix,
)
from subscription_bridge.api.openai.model_router import (
    provider_metadata,
    resolve_adapter,
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

# Per-conversation delta tracking: conversation_id -> last_msg_count_sent.
# OpenCode sends the FULL history every turn. The browser chat already has prior
# turns, so we only forward the NEW messages (delta) to avoid double context.
_conversation_delta: dict[str, int] = {}


def _delta_messages(messages: list[Any], conversation_id: str) -> tuple[list[Any], bool]:
    """Return the messages to forward plus whether the client rewrote history.

    OpenCode re-sends the entire message list every turn. The browser chat
    already contains prior turns, so forwarding the full list causes the
    browser LLM to see duplicated context (its own history + our re-sent
    history), which bloats the prompt and causes empty/refusal responses.

    Strategy: track how many messages we last sent. On the next request,
    send only the tail beyond that count. If the client rewrote/compacted
    history (count <= last_count), the browser chat is stale (e.g. OpenCode
    summarized the context) — send everything and ask the adapters to open
    a fresh browser chat.
    """
    count = len(messages)
    last_count = _conversation_delta.get(conversation_id, 0)

    if count <= last_count:
        # History was rewritten or compacted — restart the browser chat.
        _conversation_delta[conversation_id] = count
        return messages, True

    delta = messages[last_count:]
    _conversation_delta[conversation_id] = count
    return delta, False

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


_THINKING_LEVELS = {"low", "medium", "high"}


def _normalize_thinking_level(reasoning_effort: str | None) -> str | None:
    """Map OpenAI reasoning_effort values onto browser thinking levels.

    OpenCode variants for openai-compatible providers emit low/medium/high.
    Other clients may send OpenAI's extended set; clamp those to our three
    browser-controllable levels.
    """
    if not reasoning_effort:
        return None
    level = str(reasoning_effort).strip().lower()
    if level in _THINKING_LEVELS:
        return level
    if level in ("none", "minimal"):
        return "low"
    if level in ("xhigh", "max"):
        return "high"
    return None


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




def _resolve_agent_answer(result: Any) -> str:
    if result.answer:
        return str(result.answer)
    if result.needs_clarification and result.question:
        return str(result.question)
    if result.error:
        return f"Error: {result.error}"
    return "No answer generated"


def _conversation_id(
    messages: list[Any],
    request: Request | None = None,
    model: str | None = None,
) -> str:
    """Return a stable browser-conversation key without hashing mutable history.

    Prefer a host session ID when available. Otherwise use the complete system
    prompt and first user message, not a short prefix of the first few messages.
    The model id is folded into the fallback digest so a model switch restarts
    the conversation instead of appending to the previous model's transcript.
    """
    if request is not None:
        for header in ("x-opencode-session", "x-opencode-session-id", "x-session-id"):
            supplied = request.headers.get(header, "").strip()
            if supplied:
                digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()[:24]
                return f"opencode-{digest}"

    system_text: list[str] = []
    first_user = ""
    for message in messages:
        role = getattr(message, "role", "")
        content = getattr(message, "content", None)
        text = extract_text(content) if isinstance(content, (str, list)) else ""
        if role == "system":
            system_text.append(text)
        elif role == "user" and text.strip() and not first_user:
            first_user = text
    identity = "\0".join([model or "", *system_text, first_user])
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"conv-{digest}"


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
    return await resolve_adapter(model_id, deps)


@router.get("/models")
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


@router.post("/chat/completions")
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
        # Never log message contents: requests may contain credentials or source code.
        body_bytes=len(_json.dumps(body, ensure_ascii=False).encode("utf-8")),
        body_keys=sorted(body.keys()),
        reasoning_effort=body.get("reasoning_effort") or body.get("reasoningEffort"),
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

    from subscription_bridge.api.openai.model_router import ProviderUnavailableError

    try:
        provider_adapter = await _resolve_adapter(req.model, deps)
    except ProviderUnavailableError as e:
        return _error_json(str(e), code="provider_unavailable", param="model", status_code=503)
    if provider_adapter is None:
        return _error_json(
            f"Model not found: {req.model}",
            code="model_not_found",
            param="model",
        )

    has_tools = bool(req.tools) and req.tool_choice != "none"
    conversation_id = _conversation_id(req.messages, request, model=req.model)
    # Only forward NEW messages to the browser. The browser chat already has
    # prior turns; re-sending full history causes double context bloat.
    delta_msgs, history_rewritten = _delta_messages(req.messages, conversation_id)
    is_first_request = len(delta_msgs) == len(req.messages)
    prompt, system_prompt = _convert_messages(
        delta_msgs, req.tools if has_tools else None,
        tool_choice=req.tool_choice,
        require_json_tools=has_tools,
    )
    # Full transcript for the browser chat: used on the first turn and whenever
    # OpenCode compacts/rewrites history so the fresh browser chat gets the
    # post-compaction context (including the summary) in one message.
    full_prompt, full_system_prompt = _convert_messages(
        req.messages, req.tools if has_tools else None,
        tool_choice=req.tool_choice,
        require_json_tools=has_tools,
    )
    # System prompt is only needed on the first turn; the browser chat
    # persists it. On delta turns the adapter skips system_prompt anyway.
    # The first turn is delivered as two labelled sections so the browser model
    # separates background context from the operating contract. After compaction
    # the original prompt must not be re-sent in full: only a bounded reminder.
    if history_rewritten:
        system_prompt = compact_system_prompt(full_system_prompt)
    elif is_first_request:
        system_prompt = render_system_prompt(system_prompt)
    else:
        system_prompt = ""

    workspace_resolution = resolve_workspace(req, request)
    log.info("workspace_resolved", workspace=workspace_resolution.path, source=workspace_resolution.source)

    attachments: list[str] = []
    for msg in delta_msgs:
        if isinstance(msg.content, list):
            attachments.extend(_extract_images_from_content(msg.content))

    provider_metadata_dict: dict[str, Any] = {
        **provider_metadata(req.model),
        "isolated_conversation": True,
        "full_prompt": full_prompt,
        "model_id": req.model,
    }
    if history_rewritten:
        provider_metadata_dict["restart_conversation"] = True
        log.info("history_rewritten_restart", conversation_id=conversation_id, msg_count=len(req.messages))
    thinking_level = _normalize_thinking_level(req.reasoning_effort)
    if thinking_level:
        provider_metadata_dict["thinking_level"] = thinking_level

    provider_req = ProviderRequest(
        run_id=conversation_id,
        prompt=prompt,
        system_prompt=system_prompt or None,
        attachments=attachments or None,
        require_json=has_tools,
        timeout_seconds=max((req.max_completion_tokens or req.max_tokens or 1024) // 100, 30),
        metadata=provider_metadata_dict,
    )

    if req.stream:
        return StreamingResponse(
            _stream_response(
                provider_adapter, provider_req, req.model, has_tools=has_tools,
                tools=req.tools if has_tools else None, tool_choice=req.tool_choice,
                include_usage=bool((req.stream_options or {}).get("include_usage")),
                parallel_tool_calls=req.parallel_tool_calls,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # OpenAI compatibility mode is a model gateway. It may return tool_calls,
    # but it never executes local tools; clients such as OpenCode own execution.
    try:
        response = await provider_adapter.send_prompt(provider_req)
    finally:
        _cleanup_temp_files(attachments)

    if not response.success:
        return _error_json(response.error or "Provider error", code="provider_error", status_code=502)

    parsed_tool_calls = (
        parse_tool_calls(response.text, tools=req.tools, tool_choice=req.tool_choice) if has_tools else []
    )
    if req.parallel_tool_calls is False:
        parsed_tool_calls = parsed_tool_calls[:1]
    if parsed_tool_calls:
        seen_ids: set[str] = set()
        for idx, tool_call in enumerate(parsed_tool_calls, start=1):
            if not tool_call.id or tool_call.id in seen_ids:
                tool_call.id = f"call_{uuid.uuid4().hex[:20]}"
            seen_ids.add(tool_call.id)
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
    full_history: bool = False,
) -> tuple[str, str]:
    return convert_messages(messages, tools, tool_choice, require_json_tools, full_history)


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
    has_tools: bool = False,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    include_usage: bool = False,
    parallel_tool_calls: bool | None = None,
) -> AsyncGenerator[str, None]:
    try:
        async for chunk in stream_response(
            adapter, request, model, has_tools=has_tools,
            tools=tools, tool_choice=tool_choice, include_usage=include_usage,
            parallel_tool_calls=parallel_tool_calls,
        ):
            yield chunk
    finally:
        cleanup_temp_files(request.attachments or [])


async def _stream_agent_answer(answer: str, model: str) -> AsyncGenerator[str, None]:
    async for chunk in stream_agent_answer(answer, model):
        yield chunk


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    async for chunk in error_stream(message):
        yield chunk
