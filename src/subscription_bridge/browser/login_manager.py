from __future__ import annotations

import time
from typing import Any


class LoginTimeoutError(Exception):
    ...


async def wait_for_url_contains(
    page: Any,
    substring: str,
    timeout: float = 180.0,
    interval: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            url = await page.evaluate("window.location.href")
            if substring in (url or ""):
                return True
        except Exception:
            pass
        await _sleep(interval)
    return False


async def wait_for_selector_visible(
    page: Any,
    selector: str,
    timeout: float = 30.0,
) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=timeout * 1000, state="visible")
        return True
    except Exception:
        return False


async def check_login_indicator(
    page: Any,
    indicators: list[str],
) -> bool:
    for selector in indicators:
        try:
            el = await page.query_selector(selector)
            if el is not None and await el.is_visible():
                return True
        except Exception:
            continue
    return False


async def wait_for_login(
    page: Any,
    readiness_check: Any,
    timeout: float = 180.0,
    strict: bool = False,
) -> None:
    deadline = time.monotonic() + timeout
    next_log = time.monotonic() + 5

    while time.monotonic() < deadline:
        try:
            ready = await readiness_check(page)
            if ready:
                return
        except Exception:
            pass

        now = time.monotonic()
        if now >= next_log:
            next_log = now + 5

        await _sleep(1.0)

    msg = f"Timed out after {timeout}s waiting for login readiness"
    if strict:
        raise LoginTimeoutError(msg)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
