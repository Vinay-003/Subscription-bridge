from __future__ import annotations

import pytest

from subscription_bridge.browser.playwright_manager import (
    PlaywrightLaunchError,
    PlaywrightManager,
)


def test_playwright_manager_init() -> None:
    pm = PlaywrightManager({"browser": {"mode": "managed"}})
    assert pm.is_launched is False
    assert pm.context is None
    assert pm.browser is None


def test_playwright_manager_invalid_mode() -> None:
    pm = PlaywrightManager({"browser": {"mode": "invalid"}})

    with pytest.raises(PlaywrightLaunchError, match="Invalid browser mode"):
        import asyncio

        asyncio.run(pm.start())


def test_playwright_manager_cdp_not_reachable() -> None:
    pm = PlaywrightManager(
        {"browser": {"mode": "cdp", "cdp_url": "http://127.0.0.1:1"}}
    )

    with pytest.raises(
        PlaywrightLaunchError, match="Cannot reach CDP endpoint"
    ):
        import asyncio

        asyncio.run(pm.start())


def test_playwright_manager_create_page_before_start() -> None:
    pm = PlaywrightManager({"browser": {"mode": "managed"}})

    with pytest.raises(PlaywrightLaunchError, match="not started"):
        import asyncio

        asyncio.run(pm.create_page())


@pytest.mark.asyncio
async def test_cdp_create_page_claims_existing_provider_tab_before_opening_new_tab() -> None:
    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage("https://chatgpt.com/c/visible-conversation")]

        async def new_page(self) -> FakePage:
            page = FakePage("about:blank")
            self.pages.append(page)
            return page

    pm = PlaywrightManager({"browser": {"mode": "cdp"}})
    pm._mode = "cdp"
    pm._context = FakeContext()

    first = await pm.create_page("chatgpt")
    second = await pm.create_page("chatgpt")

    assert first.url == "https://chatgpt.com/c/visible-conversation"
    assert second is not first
    assert len(pm.context.pages) == 2


@pytest.mark.asyncio
async def test_cdp_create_page_navigates_claimed_blank_tab_to_provider_app() -> None:
    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

        async def goto(self, url: str, **kwargs: object) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage("chrome://newtab/")]

    pm = PlaywrightManager({"browser": {"mode": "cdp"}})
    pm._mode = "cdp"
    pm._context = FakeContext()

    page = await pm.create_page("gemini")

    assert page.url == "https://gemini.google.com/app"
    assert len(pm.context.pages) == 1


@pytest.mark.asyncio
async def test_cdp_create_page_navigates_fresh_tab_to_provider_app() -> None:
    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

        async def goto(self, url: str, **kwargs: object) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FakePage("https://chatgpt.com/c/visible-conversation")]

        async def new_page(self) -> FakePage:
            page = FakePage("about:blank")
            self.pages.append(page)
            return page

    pm = PlaywrightManager({"browser": {"mode": "cdp"}})
    pm._mode = "cdp"
    pm._context = FakeContext()

    page = await pm.create_page("gemini")

    assert page.url == "https://gemini.google.com/app"
    assert len(pm.context.pages) == 2
