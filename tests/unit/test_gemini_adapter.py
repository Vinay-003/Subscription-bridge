from __future__ import annotations

from typing import Any

import pytest

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.providers import ProviderRequest
from subscription_bridge.providers.gemini.adapter import GeminiProviderAdapter


class FakePage:
    def __init__(self) -> None:
        self._closed = False
        self._url = "about:blank"

    async def evaluate(self, expr: str) -> int | str:
        if self._closed:
            raise RuntimeError("page closed")
        if "window.location.href" in expr:
            return self._url
        return 1

    async def goto(self, url: str, **kwargs: Any) -> None:
        self._url = url

    async def close(self) -> None:
        self._closed = True

    async def screenshot(self, path: str) -> bytes:
        return b"fake"

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector)


class FakeLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> FakeLocator:
        return self

    async def is_visible(self) -> bool:
        return True

    async def wait_for(self, **kwargs: Any) -> None:
        pass

    async def click(self) -> None:
        pass

    async def scroll_into_view_if_needed(self) -> None:
        pass

    async def evaluate(self, script: str, *args: Any) -> str:
        return "test response"

    async def fill(self, value: str) -> None:
        pass

    async def press(self, key: str) -> None:
        pass


async def page_factory() -> FakePage:
    return FakePage()


class FakeGeminiPage:
    def __init__(self) -> None:
        self._url = "about:blank"
        self._responses: list[str] = []

    async def evaluate(self, expr: str, *args: Any) -> Any:
        if "window.location.href" in expr:
            return "https://gemini.google.com/app"
        if "innerText" in expr or "textContent" in expr or "response" in expr.lower():
            return "test assistant response content"
        if "stopVisible" in expr or "thinking" in expr:
            return {
                "stopVisible": False,
                "thinkingVisible": False,
                "progressVisible": False,
                "assistantCount": 1,
                "conversationUrl": True,
                "path": "/app/new-chat",
            }
        return 1

    async def goto(self, url: str, **kwargs: Any) -> None:
        pass

    async def close(self) -> None:
        pass

    async def screenshot(self, path: str) -> bytes:
        return b"fake"

    def locator(self, selector: str) -> FakeGeminiLocator:
        return FakeGeminiLocator(selector)

    async def keyboard(self) -> None:
        pass


class FakeGeminiLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> FakeGeminiLocator:
        return self

    async def is_visible(self) -> bool:
        return True

    async def wait_for(self, **kwargs: Any) -> None:
        pass

    async def click(self) -> None:
        pass

    async def scroll_into_view_if_needed(self) -> None:
        pass

    async def evaluate(self, script: str, *args: Any) -> str:
        if "readText" in script or "innerText" in script or "textContent" in script:
            return "test response text"
        return "test response text"

    async def fill(self, value: str) -> None:
        pass

    async def press(self, key: str) -> None:
        pass

    async def insert_text(self, text: str) -> None:
        pass


class CompleteGeminiPage(FakeGeminiPage):
    async def evaluate(self, expr: str, *args: Any) -> Any:
        if "window.location.href" in expr:
            return "https://gemini.google.com/app"
        if "stopVisible" in expr or "conversationUrl" in expr:
            return {
                "stopVisible": False,
                "thinkingVisible": False,
                "progressVisible": False,
                "assistantCount": 2,
                "conversationUrl": True,
                "path": "/app/new-chat",
            }
        if "response" in expr.lower() and "selector" in expr:
            return "latest assistant response from gemini"
        return "test response"


async def gemini_page_factory() -> CompleteGeminiPage:
    return CompleteGeminiPage()


@pytest.mark.asyncio
async def test_adapter_creation() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=page_factory)
    assert adapter.name == "gemini"
    assert "text_chat" in adapter.capabilities
    assert "code_reasoning" in adapter.capabilities
    assert "image_generation" not in adapter.capabilities


@pytest.mark.asyncio
async def test_adapter_create_session() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=gemini_page_factory)
    session_id = await adapter.create_session()
    assert session_id is not None
    assert len(session_id) > 0


@pytest.mark.asyncio
async def test_adapter_session_lifecycle() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=gemini_page_factory)

    session_id = await adapter.create_session()
    assert pool.get_session(session_id) is not None

    await adapter.close_session(session_id)
    assert pool.get_session(session_id) is None


@pytest.mark.asyncio
async def test_adapter_send_prompt_fails_without_browser() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)

    async def failing_factory() -> FakePage:
        return FakePage()

    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=failing_factory)
    request = ProviderRequest(run_id="test-001", prompt="say hello", timeout_seconds=5)
    response = await adapter.send_prompt(request)
    assert response.success is False
    assert not response.text


@pytest.mark.asyncio
async def test_adapter_health_check() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=gemini_page_factory)
    ok = await adapter.health_check()
    assert ok is False  # mock page doesn't fully satisfy all health checks


@pytest.mark.asyncio
async def test_adapter_reset_chat() -> None:
    pool = SessionPool(max_sessions=3, session_ttl_seconds=600)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=gemini_page_factory)
    session_id = "test-session"
    await adapter.reset_chat(session_id)
    await adapter.reset_chat("all")


@pytest.mark.asyncio
async def test_adapter_capabilities() -> None:
    assert "text_chat" in GeminiProviderAdapter.capabilities
    assert "code_reasoning" in GeminiProviderAdapter.capabilities
    assert "file_upload" in GeminiProviderAdapter.capabilities
    assert "vision" in GeminiProviderAdapter.capabilities
    assert "image_generation" not in GeminiProviderAdapter.capabilities
