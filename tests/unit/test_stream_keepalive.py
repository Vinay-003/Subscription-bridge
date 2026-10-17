from __future__ import annotations

import asyncio
import json
from typing import Any

from subscription_bridge.api.openai import streaming
from subscription_bridge.api.openai.streaming import stream_response
from subscription_bridge.providers.base import ProviderRequest, ProviderResponse


def _request() -> ProviderRequest:
    return ProviderRequest(run_id="keepalive-test", prompt="User: hello")


class SlowAdapter:
    def __init__(self, delay: float = 0.2, text: str = "done") -> None:
        self.delay = delay
        self.text = text

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        await asyncio.sleep(self.delay)
        return ProviderResponse(
            provider="fake", text=self.text, raw_text=self.text, success=True, latency_seconds=0.0,
        )


class FailingAdapter:
    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        await asyncio.sleep(0)
        raise RuntimeError("browser tab lost")


class HangingAdapter:
    def __init__(self) -> None:
        self.cancelled = asyncio.Event()

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ProviderResponse(
            provider="fake", text="never", raw_text="never", success=True, latency_seconds=0.0,
        )


async def test_slow_provider_emits_sse_keepalive_comments(monkeypatch: Any) -> None:
    monkeypatch.setattr(streaming, "KEEPALIVE_INTERVAL_SECONDS", 0.02)
    chunks = [chunk async for chunk in stream_response(SlowAdapter(), _request(), "fake")]
    assert any(chunk.startswith(": keepalive") for chunk in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"
    payloads = [json.loads(c[6:]) for c in chunks if c.startswith("data: ") and "[DONE]" not in c]
    assert any(p.get("choices") for p in payloads)


async def test_fast_provider_returns_without_keepalive(monkeypatch: Any) -> None:
    monkeypatch.setattr(streaming, "KEEPALIVE_INTERVAL_SECONDS", 5.0)
    chunks = [chunk async for chunk in stream_response(SlowAdapter(delay=0.0), _request(), "fake")]
    assert not any(chunk.startswith(": keepalive") for chunk in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


async def test_adapter_exception_becomes_sse_error_payload() -> None:
    chunks = [chunk async for chunk in stream_response(FailingAdapter(), _request(), "fake")]
    error_chunks = [c for c in chunks if c.startswith("data: ")]
    payload = json.loads(error_chunks[0][6:])
    assert payload["error"]["type"] == "provider_error"
    assert "browser tab lost" in payload["error"]["message"]
    assert chunks[-1] == "data: [DONE]\n\n"


async def test_closing_stream_cancels_provider_task(monkeypatch: Any) -> None:
    monkeypatch.setattr(streaming, "KEEPALIVE_INTERVAL_SECONDS", 0.02)
    adapter = HangingAdapter()
    stream = stream_response(adapter, _request(), "fake")
    assert (await anext(stream)).startswith(": keepalive")
    await stream.aclose()
    await asyncio.sleep(0.05)
    assert adapter.cancelled.is_set()
