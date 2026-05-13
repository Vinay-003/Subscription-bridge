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
