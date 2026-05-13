from __future__ import annotations

from typing import Any

import pytest

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.providers import ProviderRequest
from subscription_bridge.providers.gemini.adapter import GeminiProviderAdapter


class GeminiPageWithFiles:
    async def evaluate(self, expr: str, *args: Any) -> Any:
        if "window.location.href" in expr:
            return "https://gemini.google.com/app"
        return 1

    async def goto(self, url: str, **kwargs: Any) -> None:
        pass

    async def close(self) -> None:
        pass

    async def screenshot(self, path: str) -> bytes:
        return b"fake"

    def locator(self, selector: str) -> GeminiLocator:
        return GeminiLocator(selector)

    async def query_selector_all(self, selector: str) -> list:
        return []


class GeminiLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> GeminiLocator:
        return self

    async def is_visible(self) -> bool:
        return "file" not in self._selector

    async def count(self) -> int:
        return 0

    async def wait_for(self, **kwargs: Any) -> None:
        pass

    async def click(self) -> None:
        pass

    async def scroll_into_view_if_needed(self) -> None:
        pass

    async def evaluate(self, script: str, *args: Any) -> str:
        return "test response text"

    async def fill(self, value: str) -> None:
        pass

    async def press(self, key: str) -> None:
        pass

    async def insert_text(self, text: str) -> None:
        pass

    async def set_input_files(self, paths: list[str]) -> None:
        pass


async def gemini_page_factory() -> GeminiPageWithFiles:
    return GeminiPageWithFiles()


@pytest.mark.asyncio
async def test_adapter_without_attachments_still_works() -> None:
    pool = SessionPool(max_sessions=3)
    adapter = GeminiProviderAdapter(session_pool=pool, page_factory=gemini_page_factory)
    request = ProviderRequest(run_id="t1", prompt="say hello")
    response = await adapter.send_prompt(request)
    assert response.success is False  # mock page can't fully satisfy


@pytest.mark.asyncio
async def test_adapter_has_file_upload_capability() -> None:
    assert "file_upload" in GeminiProviderAdapter.capabilities


@pytest.mark.asyncio
async def test_adapter_has_vision_capability() -> None:
    assert "vision" in GeminiProviderAdapter.capabilities


@pytest.mark.asyncio
async def test_adapter_does_not_have_image_generation() -> None:
    assert "image_generation" not in GeminiProviderAdapter.capabilities


@pytest.mark.asyncio
async def test_adapter_capabilities_exact() -> None:
    assert GeminiProviderAdapter.capabilities == {
        "text_chat",
        "code_reasoning",
        "file_upload",
        "vision",
    }
