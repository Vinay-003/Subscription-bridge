from __future__ import annotations

from typing import Any

import pytest

import subscription_bridge.providers.gemini.adapter as gemini_adapter

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.providers import ProviderRequest
from subscription_bridge.providers.gemini.adapter import (
    GeminiProviderAdapter,
    _detect_model_label,
    _extract_model_variant,
    _switch_model_variant,
)
from subscription_bridge.providers.gemini.response_reader import _clean_assistant_text


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

    async def count(self) -> int:
        return 1

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

    async def count(self) -> int:
        return 1

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


class FakeToggleLocator:
    def __init__(self) -> None:
        self.clicks = 0

    @property
    def first(self) -> FakeToggleLocator:
        return self

    async def is_visible(self) -> bool:
        return True

    async def count(self) -> int:
        return 1

    async def click(self) -> None:
        self.clicks += 1


class ModelSwitchPage:
    def __init__(self, should_click: bool = True) -> None:
        self.should_click = should_click
        self.switch_calls: list[list[str]] = []
        self.locator_calls: list[str] = []

    def locator(self, selector: str) -> FakeToggleLocator:
        self.locator_calls.append(selector)
        return FakeToggleLocator()

    async def evaluate(self, expr: str, *args: Any) -> Any:
        if "aliases" in expr and "menuitem" in expr:
            if args and isinstance(args[0], list):
                self.switch_calls.append([str(a) for a in args[0]])
            return self.should_click
        if "gemini" in expr.lower():
            return "Gemini 3 Flash"
        return 1

    async def keyboard(self) -> None:
        pass


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


def test_extract_model_variant_from_metadata() -> None:
    request = ProviderRequest(
        run_id="test-variant",
        prompt="hello",
        metadata={"gemini_model_variant": "Gemini 3 Flash"},
    )
    assert _extract_model_variant(request) == "Gemini 3 Flash"


def test_extract_model_variant_from_prompt_header() -> None:
    request = ProviderRequest(
        run_id="test-variant",
        prompt="[Model: Gemini 3.1 Pro]\nhello",
    )
    assert _extract_model_variant(request) == "Gemini 3.1 Pro"


def test_extract_model_variant_from_non_first_line() -> None:
    request = ProviderRequest(
        run_id="test-variant",
        prompt="Conversation:\nUser: hi\n[Model: Gemini 3 Flash]\nUser: sup",
    )
    assert _extract_model_variant(request) == "Gemini 3 Flash"


@pytest.mark.asyncio
async def test_switch_model_variant_clicks_menu_and_option() -> None:
    page = ModelSwitchPage(should_click=True)
    async def _always(page: Any, labels: list[str], **kwargs: Any) -> bool:
        return True
    gemini_adapter.safe_click_labels = _always  # type: ignore[assignment]
    async def _dismiss(page: Any) -> None:
        return None
    gemini_adapter.dismiss_overlays = _dismiss  # type: ignore[assignment]
    ok = await _switch_model_variant(page, "Gemini 3 Flash")
    assert ok is True


@pytest.mark.asyncio
async def test_switch_model_variant_fails_when_no_match() -> None:
    page = ModelSwitchPage(should_click=False)
    async def _never(page: Any, labels: list[str], **kwargs: Any) -> bool:
        return False
    gemini_adapter.safe_click_labels = _never  # type: ignore[assignment]
    async def _dismiss(page: Any) -> None:
        return None
    gemini_adapter.dismiss_overlays = _dismiss  # type: ignore[assignment]
    ok = await _switch_model_variant(page, "Gemini 3 Flash")
    assert ok is False


@pytest.mark.asyncio
async def test_detect_model_label_reads_visible_text() -> None:
    page = ModelSwitchPage(should_click=True)
    label = await _detect_model_label(page)
    assert "Gemini" in label


def test_clean_assistant_text_filters_stopped_message() -> None:
    assert _clean_assistant_text("You stopped this response") == ""
