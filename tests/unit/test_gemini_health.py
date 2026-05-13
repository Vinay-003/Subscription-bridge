from __future__ import annotations

from typing import Any

import pytest

from subscription_bridge.providers.gemini.health import (
    _url_is_app,
    check_composer_visible,
    check_gemini_reachable,
    check_login_indicator,
    check_temporary_chat,
)


class ReadyPage:
    async def evaluate(self, script: str) -> str | bool:
        if "temporary" in script.lower() or "headings" in script.lower():
            return False
        return "https://gemini.google.com/app"

    def locator(self, selector: str) -> ReadyLocator:
        return ReadyLocator(selector)


class ReadyLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> ReadyLocator:
        return self

    async def is_visible(self) -> bool:
        return True

    async def wait_for(self, **kwargs: Any) -> None:
        pass


class NotReachablePage:
    async def evaluate(self, script: str) -> str:
        return "about:blank"

    def locator(self, selector: str) -> NotReachableLocator:
        return NotReachableLocator(selector)


class NotReachableLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> NotReachableLocator:
        return self

    async def is_visible(self) -> bool:
        return False

    async def wait_for(self, **kwargs: Any) -> None:
        raise RuntimeError("not found")


class TemporaryChatPage:
    async def evaluate(self, script: str) -> bool:
        return True

    def locator(self, selector: str) -> TemporaryChatLocator:
        return TemporaryChatLocator(selector)


class TemporaryChatLocator:
    def __init__(self, selector: str) -> None:
        self._selector = selector

    @property
    def first(self) -> TemporaryChatLocator:
        return self

    async def is_visible(self) -> bool:
        return True

    async def wait_for(self, **kwargs: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_gemini_reachable_ready() -> None:
    ok = await check_gemini_reachable(ReadyPage())
    assert ok is True


@pytest.mark.asyncio
async def test_gemini_reachable_not_reachable() -> None:
    ok = await check_gemini_reachable(NotReachablePage())
    assert ok is False


@pytest.mark.asyncio
async def test_composer_visible_ready() -> None:
    ok = await check_composer_visible(ReadyPage())
    assert ok is True


@pytest.mark.asyncio
async def test_composer_visible_not_ready() -> None:
    ok = await check_composer_visible(NotReachablePage())
    assert ok is False


@pytest.mark.asyncio
async def test_check_login_indicator_ready() -> None:
    ok = await check_login_indicator(ReadyPage())
    # ReadyLocator returns is_visible() = True for all locators
    assert ok is True


@pytest.mark.asyncio
async def test_check_login_indicator_not_ready() -> None:
    ok = await check_login_indicator(NotReachablePage())
    assert ok is False


@pytest.mark.asyncio
async def test_check_temporary_chat_true() -> None:
    page = TemporaryChatPage()
    ok = await check_temporary_chat(page)
    assert ok is True


@pytest.mark.asyncio
async def test_check_temporary_chat_false() -> None:
    page = ReadyPage()
    ok = await check_temporary_chat(page)
    assert ok is False


def test_url_is_app() -> None:
    assert _url_is_app("https://gemini.google.com/app") is True
    assert _url_is_app("https://gemini.google.com/app?query=1") is True


def test_url_is_not_app() -> None:
    assert _url_is_app("https://gemini.google.com/app/old-chat") is False
    assert _url_is_app("https://other.com/") is False
    assert _url_is_app("about:blank") is False
