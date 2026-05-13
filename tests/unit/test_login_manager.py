from __future__ import annotations

import pytest

from subscription_bridge.browser.login_manager import (
    LoginTimeoutError,
    check_login_indicator,
    wait_for_login,
)


class FakePage:
    def __init__(self) -> None:
        self._ready = False

    async def query_selector(self, selector: str) -> FakeElement | None:
        if selector == ".login-indicator":
            return FakeElement(visible=self._ready)
        return None


class FakeElement:
    def __init__(self, visible: bool = True) -> None:
        self._visible = visible

    async def is_visible(self) -> bool:
        return self._visible


@pytest.mark.asyncio
async def test_check_login_indicator_found() -> None:
    page = FakePage()
    page._ready = True
    result = await check_login_indicator(page, [".login-indicator"])
    assert result is True


@pytest.mark.asyncio
async def test_check_login_indicator_not_found() -> None:
    page = FakePage()
    page._ready = False
    result = await check_login_indicator(page, [".login-indicator"])
    assert result is False


@pytest.mark.asyncio
async def test_check_login_indicator_empty_selectors() -> None:
    page = FakePage()
    result = await check_login_indicator(page, [])
    assert result is False


@pytest.mark.asyncio
async def test_wait_for_login_strict_timeout() -> None:
    page = FakePage()

    async def check(p: FakePage) -> bool:
        return False

    with pytest.raises(LoginTimeoutError, match="Timed out"):
        await wait_for_login(page, check, timeout=0.1, strict=True)
