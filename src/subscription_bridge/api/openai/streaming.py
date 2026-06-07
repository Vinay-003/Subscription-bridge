from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from subscription_bridge.api.openai.tool_parser import parse_tool_calls
from subscription_bridge.api.openai_models import ChatCompletionChunk, ChoiceDelta, DeltaMessage
from subscription_bridge.providers.base import ProviderRequest


async def stream_response(
    adapter: Any,
    request: ProviderRequest,
    model: str,
    has_tools: bool = False,
) -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    yield _completion_chunk(completion_id, now, model, role="assistant")

    response = await adapter.send_prompt(request)

    if not response.success:
        yield _completion_chunk(completion_id, now, model, content=f"Error: {response.error}", finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    if has_tools and response.text:
        tool_calls = parse_tool_calls(response.text)
        if tool_calls:
            async for chunk in stream_tool_calls(tool_calls, completion_id, now, model):
                yield chunk
            yield _completion_chunk(completion_id, now, model, finish_reason="tool_calls")
            yield "data: [DONE]\n\n"
            return

    if response.text:
        async for chunk in stream_text(response.text, completion_id, now, model):
            yield chunk

    yield _completion_chunk(completion_id, now, model, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def stream_agent_answer(answer: str, model: str) -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    yield _completion_chunk(completion_id, now, model, role="assistant")

    if answer:
        async for chunk in stream_text(answer, completion_id, now, model):
            yield chunk

    yield _completion_chunk(completion_id, now, model, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def error_stream(message: str) -> AsyncGenerator[str, None]:
    yield _completion_chunk("error", int(time.time()), "unknown", content=f"Error: {message}", finish_reason="stop")
    yield "data: [DONE]\n\n"


async def stream_text(text: str, completion_id: str, created: int, model: str) -> AsyncGenerator[str, None]:
    chunk_size = max(len(text) // 10, 5)
    for i in range(0, len(text), chunk_size):
        yield _completion_chunk(completion_id, created, model, content=text[i : i + chunk_size])
        await asyncio.sleep(0.01)


async def stream_tool_calls(
    tool_calls: list[Any], completion_id: str, created: int, model: str,
) -> AsyncGenerator[str, None]:
    for idx, tc in enumerate(tool_calls):
        tc_id = tc.id or f"call_{idx + 1}"
        name = tc.function.name if hasattr(tc, "function") and tc.function else getattr(tc, "tool_name", "")
        args_raw = tc.function.arguments if hasattr(tc, "function") and tc.function else ""
        args_str = args_raw if isinstance(args_raw, str) else json.dumps(args_raw, default=str)

        yield _tool_call_start(completion_id, created, model, index=idx, tool_call_id=tc_id, function_name=name)

        chunk_size = max(len(args_str) // 5, 10)
        for i in range(0, len(args_str), chunk_size):
            yield _tool_call_arguments_chunk(
                completion_id, created, model, index=idx, arguments=args_str[i : i + chunk_size],
            )
            await asyncio.sleep(0.01)


def _completion_chunk(
    completion_id: str,
    created: int,
    model: str,
    role: str | None = None,
    content: str | None = None,
    finish_reason: str | None = None,
) -> str:
    chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChoiceDelta(
                index=0,
                delta=DeltaMessage(role=role, content=content),
                finish_reason=finish_reason,
            )
        ],
    )
    return f"data: {chunk.model_dump_json()}\n\n"


def _tool_call_start(
    completion_id: str,
    created: int,
    model: str,
    index: int,
    tool_call_id: str,
    function_name: str,
) -> str:
    chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChoiceDelta(
                index=0,
                delta=DeltaMessage(
                    tool_calls=[{
                        "index": index,
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": function_name, "arguments": ""},
                    }]
                ),
                finish_reason=None,
            )
        ],
    )
    return f"data: {chunk.model_dump_json()}\n\n"


def _tool_call_arguments_chunk(
    completion_id: str,
    created: int,
    model: str,
    index: int,
    arguments: str,
) -> str:
    chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChoiceDelta(
                index=0,
                delta=DeltaMessage(
                    tool_calls=[{
                        "index": index,
                        "function": {"arguments": arguments},
                    }]
                ),
                finish_reason=None,
            )
        ],
    )
    return f"data: {chunk.model_dump_json()}\n\n"
