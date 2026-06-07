from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from subscription_bridge.api.openai_models import ChatCompletionChunk, ChoiceDelta, DeltaMessage
from subscription_bridge.providers.base import ProviderRequest


async def stream_response(adapter: Any, request: ProviderRequest, model: str) -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    yield _completion_chunk(completion_id, now, model, role="assistant")

    response = await adapter.send_prompt(request)
    if response.success and response.text:
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
