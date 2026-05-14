from __future__ import annotations

from typing import Any

from subscription_bridge.providers.gemini.selectors import gemini_url, get_selector


async def check_gemini_reachable(page: Any) -> bool:
    try:
        url = await page.evaluate("window.location.href")
        return "gemini.google.com" in str(url)
    except Exception:
        return False


async def check_app_page(page: Any) -> bool:
    try:
        url = await page.evaluate("window.location.href")
        parsed = str(url).rstrip("/")
        return parsed.endswith("/app") or "/app?" in parsed
    except Exception:
        return False


async def check_composer_visible(page: Any) -> bool:
    composers = get_selector("composer")
    for selector in composers:
        try:
            el = page.locator(selector).first
            visible = await el.is_visible()
            if visible:
                return True
        except Exception:
            continue
    return False


async def check_login_indicator(page: Any) -> bool:
    indicators = get_selector("login_indicators")
    for selector in indicators:
        try:
            el = page.locator(selector).first
            visible = await el.is_visible()
            if visible:
                return True
        except Exception:
            continue
    return False


async def check_temporary_chat(page: Any) -> bool:
    script = r"""
    () => {
        const headings = Array.from(document.querySelectorAll(
            'main h1, main h2, header h1, header h2, [role="heading"]'
        ));
        for (const h of headings) {
            const t = (h.innerText || h.textContent || '').trim().toLowerCase();
            const r = h.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && t === 'temporary chat') return true;
        }
        const title = (document.title || '').toLowerCase();
        return title.includes('temporary chat');
    }
    """
    try:
        return bool(await page.evaluate(script))
    except Exception:
        return False


async def check_gemini_ready(page: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "reachable": False,
        "app_page": False,
        "logged_in": False,
        "composer_ready": False,
        "temporary_chat": False,
        "ready": False,
        "needs_login": False,
        "needs_login_detail": "",
    }

    try:
        url = await page.evaluate("window.location.href")
        url_str = str(url)
        result["reachable"] = "gemini.google.com" in url_str
        result["app_page"] = _url_is_app(url_str)
        if not result["reachable"]:
            if "accounts.google.com" in url_str:
                result["needs_login_detail"] = (
                    "Browser is on Google login page. Log in to your Google account."
                )
            else:
                result["needs_login_detail"] = (
                    f"Page URL is {url_str[:80]}, expected gemini.google.com/app. "
                    "Open Chrome and navigate there manually."
                )
    except Exception:
        result["needs_login_detail"] = "Could not read page URL"

    if not result["reachable"]:
        result["needs_login"] = True
        return result

    result["composer_ready"] = await check_composer_visible(page)
    result["logged_in"] = result["composer_ready"] or await check_login_indicator(page)
    result["temporary_chat"] = await check_temporary_chat(page)

    result["ready"] = result["app_page"] and result["logged_in"] and not result["temporary_chat"]
    result["needs_login"] = not result["logged_in"]
    if result["needs_login"]:
        result["needs_login_detail"] = "Gemini app loaded but no composer found. Log in to your Google account."

    return result


async def check_provider_health(page: Any) -> dict[str, Any]:
    result = await check_gemini_ready(page)

    if not result["reachable"]:
        return {"status": "unreachable", "detail": "Cannot reach gemini.google.com", "checks": result}

    if result["temporary_chat"]:
        return {"status": "degraded", "detail": "Temporary Chat mode is active", "checks": result}

    if result["needs_login"]:
        return {"status": "needs_login", "detail": "User must log in to Gemini", "checks": result}

    if result["ready"]:
        return {"status": "ready", "detail": "Gemini is ready", "checks": result}

    return {"status": "unknown", "detail": "Gemini reachable but state unclear", "checks": result}


async def navigate_to_gemini(page: Any) -> None:
    from playwright.async_api import TimeoutError as PWTimeoutError

    url = gemini_url()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except PWTimeoutError:
        current = ""
        try:
            current = await page.evaluate("window.location.href")
        except Exception:
            pass
        if "gemini.google.com" in current:
            return
        raise


async def navigate_to_fresh_chat(page: Any) -> None:
    await navigate_to_gemini(page)


def _url_is_app(url: str) -> bool:
    if "gemini.google.com" not in url:
        return False
    path = url.rstrip("/")
    return path.endswith("/app") or "/app?" in path


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
