from __future__ import annotations

import time
from typing import Any

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.browser.tab_session import TabSession
from subscription_bridge.browser.ui_guard import dismiss_overlays
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.providers.base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderRequest,
    ProviderResponse,
)

logger = get_logger("provider.chatgpt")

CHATGPT_URL = "https://chatgpt.com/"


class ChatGPTProviderAdapter(ProviderAdapter):
    name = "chatgpt"
    capabilities: set[ProviderCapability] = {"text_chat", "code_reasoning", "file_upload", "vision"}

    def __init__(self, session_pool: SessionPool, page_factory: Any) -> None:
        self._pool = session_pool
        self._page_factory = page_factory

    async def create_session(self) -> str:
        session = await self._pool.acquire("chatgpt", "", self._page_factory)
        return session.session_id

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        start = time.monotonic()
        session: TabSession | None = None
        upload_meta: dict[str, Any] | None = None
        prompt = request.prompt
        logger = get_logger("provider.chatgpt")

        try:
            session = await self._pool.acquire("chatgpt", request.run_id, self._page_factory)

            requested_variant = _extract_model_variant(request)
            if requested_variant and session.selected_model_variant != requested_variant:
                logger.info(
                    "model_switch_requested",
                    requested=requested_variant,
                    run_id=request.run_id,
                )
                switched = await _switch_chatgpt_model(session.page, requested_variant)
                session.selected_model_variant = requested_variant if switched else None
                logger.info(
                    "model_switch_done",
                    requested=requested_variant,
                    switched=switched,
                    run_id=request.run_id,
                )

            is_continuation = session.has_active_conversation

            if not is_continuation:
                await self._ensure_fresh_chat(session)

            await _find_composer(session.page)
            await _set_prompt_text(session.page, prompt)
            await _submit_via_enter(session.page)
            logger.info("send_method_used", method="enter", run_id=request.run_id)

            accepted = await _wait_for_send_confirmation(session.page, timeout=20.0)
            if not accepted:
                await _click_send_button(session.page)
                accepted = await _wait_for_send_confirmation(session.page, timeout=25.0)

            if not accepted:
                await session.screenshot_debug("send_not_confirmed")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="ChatGPT did not confirm prompt submission",
                    metadata=upload_meta or {},
                )

            complete = await _wait_for_response_complete(session.page, timeout=180.0)
            if not complete:
                await session.screenshot_debug("response_timeout")
                text = await _extract_latest_assistant_text(session.page)
                if text:
                    return ProviderResponse(
                        provider=self.name, text=text, raw_text=text, success=True,
                        latency_seconds=time.monotonic() - start,
                        metadata=upload_meta or {},
                    )
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="ChatGPT did not produce a response within timeout",
                    metadata=upload_meta or {},
                )

            text = await _extract_latest_assistant_text(session.page)
            if not text:
                await session.screenshot_debug("empty_response")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="ChatGPT returned empty response",
                    metadata=upload_meta or {},
                )

            session.has_active_conversation = True

            return ProviderResponse(
                provider=self.name, text=text, raw_text=text, success=True,
                latency_seconds=time.monotonic() - start,
                metadata=upload_meta or {},
            )

        except Exception as e:
            if session is not None:
                await session.screenshot_debug("provider_error")
            return ProviderResponse(
                provider=self.name, text="", raw_text="", success=False,
                latency_seconds=time.monotonic() - start,
                error=f"ChatGPT provider error: {e}", metadata=upload_meta or {},
            )
        finally:
            if session is not None:
                await self._pool.release(session.session_id)

    async def reset_chat(self, session_id: str) -> None:
        if session_id == "all":
            for s in self._pool.list_sessions():
                sid = s["session_id"]
                session_obj = self._pool.get_session(sid)
                if session_obj is not None and session_obj.provider_name == "chatgpt":
                    await self._pool.reset(sid)
        else:
            await self._pool.reset(session_id)

    async def health_check(self) -> bool:
        try:
            session = await self._pool.acquire("chatgpt", "health-check", self._page_factory)
            try:
                page = session.page
                await page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
                ready = await _chatgpt_app_ready(page)
                return ready
            finally:
                await self._pool.release(session.session_id)
        except Exception:
            return False

    async def detailed_health(self) -> dict[str, Any]:
        session = await self._pool.acquire("chatgpt", "detailed-health", self._page_factory)
        try:
            page = session.page
            await page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
            ready = await _chatgpt_app_ready(page)
            return {
                "status": "ready" if ready else "unknown",
                "checks": {
                    "reachable": True,
                    "app_page": ready,
                    "composer_ready": ready,
                },
            }
        finally:
            await self._pool.release(session.session_id)

    async def close_session(self, session_id: str) -> None:
        await self._pool.close(session_id)

    async def _ensure_fresh_chat(self, session: TabSession) -> None:
        import asyncio
        page = session.page
        try:
            await page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(2.0)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            ready = await _chatgpt_app_ready(page)
            if ready:
                await dismiss_overlays(page)
                return
            await asyncio.sleep(1.0)


async def _chatgpt_app_ready(page: Any) -> bool:
    try:
        current = (page.url or "").lower()
    except Exception:
        return False
    if "chatgpt.com" not in current and "chat.openai.com" not in current:
        return False
    selectors = [
        "#prompt-textarea",
        "textarea[data-testid='prompt-textarea']",
        "[data-testid='composer'] textarea",
        "[data-testid='composer'] [contenteditable='true']",
        "div.ProseMirror[contenteditable='true']",
        "main div[contenteditable='true']",
        "textarea",
    ]
    for selector in selectors:
        try:
            if await page.locator(selector).first.is_visible():
                return True
        except Exception:
            continue
    return False


async def _find_composer(page: Any, timeout: int = 30) -> Any:
    selectors = [
        "#prompt-textarea",
        "textarea[data-testid='prompt-textarea']",
        "[data-testid='composer'] textarea",
        "[data-testid='composer'] [contenteditable='true']",
        "div.ProseMirror[contenteditable='true']",
        "main form textarea",
        "main form [contenteditable='true']",
        "main div[contenteditable='true']",
        "textarea",
    ]
    import asyncio
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Could not find ChatGPT composer within {timeout}s")


async def _set_prompt_text(page: Any, text: str) -> None:
    composer = await _find_composer(page)
    try:
        await composer.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    try:
        await composer.click(timeout=5000)
    except Exception:
        pass
    import asyncio
    await asyncio.sleep(0.15)
    try:
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    await asyncio.sleep(0.25)
    try:
        await page.keyboard.insert_text(text)
    except Exception:
        pass


async def _submit_via_enter(page: Any) -> None:
    composer = await _find_composer(page, timeout=5)
    try:
        await composer.click(timeout=3000)
    except Exception:
        pass
    await page.keyboard.press("Enter")


async def _click_send_button(page: Any) -> bool:
    selectors = [
        "button[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[type='submit']",
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                return True
        except Exception:
            continue
    return False


async def _wait_for_send_confirmation(page: Any, timeout: float = 20.0) -> bool:
    import asyncio
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            composer_text = await _get_composer_text(page)
            if not composer_text.strip():
                return True
        except Exception:
            pass
        try:
            current_url = page.url or ""
            if "/c/" in current_url:
                return True
        except Exception:
            pass
        report = await _submission_activity_report(page)
        if report.get("stopVisible") or report.get("thinkingVisible") or report.get("progressVisible"):
            return True
        if report.get("assistantCount", 0) > 0:
            return True
        await asyncio.sleep(0.5)
    return False


async def _wait_for_response_complete(page: Any, timeout: float = 180.0) -> bool:
    import asyncio
    deadline = time.monotonic() + timeout
    last_count = 0
    stable_cycles = 0
    while time.monotonic() < deadline:
        report = await _submission_activity_report(page)
        current_count = report.get("assistantCount", 0)
        is_generating = report.get("stopVisible") or report.get("progressVisible")

        if not is_generating:
            if current_count > last_count:
                stable_cycles += 1
                if stable_cycles >= 3:
                    return True
            else:
                if current_count > 0:
                    stable_cycles += 1
                    if stable_cycles >= 3:
                        return True
            last_count = current_count
        else:
            stable_cycles = 0

        await asyncio.sleep(0.5)
    return False


async def _extract_latest_assistant_text(page: Any) -> str:
    selectors = [
        "[data-message-author-role='assistant']",
        ".markdown",
        ".prose",
    ]
    for selector in selectors:
        try:
            script = r"""
    (selector) => {
        const elements = Array.from(document.querySelectorAll(selector));
        if (!elements.length) return '';
        const lastEl = elements[elements.length - 1];
        const rect = lastEl.getBoundingClientRect();
        const style = getComputedStyle(lastEl);
        if (rect.width === 0 || rect.height === 0 ||
            style.display === 'none' || style.visibility === 'hidden') {
            return '';
        }
        return lastEl.innerText || lastEl.textContent || '';
    }
            """
            text = await page.evaluate(script, selector)
            if text and str(text).strip():
                return str(text).strip()
        except Exception:
            continue
    return ""


async def _get_composer_text(page: Any) -> str:
    script = r"""
    () => {
        const el = document.querySelector(
            '#prompt-textarea, textarea[data-testid="prompt-textarea"], ' +
            '[data-testid="composer"] textarea, ' +
            'div.ProseMirror[contenteditable="true"], ' +
            'main div[contenteditable="true"], textarea'
        );
        if (!el) return '';
        const tag = (el.tagName || '').toLowerCase();
        if (tag === 'textarea' || tag === 'input') return el.value || '';
        if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
            return el.innerText || el.textContent || '';
        }
        return '';
    }
    """
    try:
        return str(await page.evaluate(script) or "")
    except Exception:
        return ""


async def _submission_activity_report(page: Any) -> dict[str, Any]:
    script = r"""
    () => {
        const root = document.querySelector('main') || document.body;
        function visible(el) {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        function textOf(el) {
            return ((el.getAttribute('aria-label') || '') + ' ' +
                    (el.getAttribute('title') || '') + ' ' +
                    (el.innerText || '') + ' ' +
                    (el.textContent || '')).replace(/\s+/g, ' ').trim().toLowerCase();
        }
        const buttons = Array.from(document.querySelectorAll('button, [role="button"]')).filter(visible);
        const buttonText = buttons.map(textOf).join(' | ');
        const stopVisible = buttonText.includes('stop generating') ||
            buttonText.includes('stop streaming') ||
            buttonText.includes('stop responding');
        const thinkingVisible = buttonText.includes('thinking') ||
            buttonText.includes('creating image') ||
            buttonText.includes('generating');
        let progressVisible = false;
        for (const el of document.querySelectorAll(
            '[role="progressbar"], [class*="spinner"], [class*="loading"]'
        )) {
            if (visible(el)) { progressVisible = true; break; }
        }
        const responseSelectors = [
            '[data-message-author-role="assistant"]',
            '.markdown',
            '.prose',
            '[data-testid*="conversation-turn"]',
            'article'
        ];
        let assistantCount = 0;
        for (const sel of responseSelectors) {
            for (const el of document.querySelectorAll(sel)) {
                if (visible(el)) assistantCount++;
            }
        }
        return {stopVisible, thinkingVisible, progressVisible, assistantCount};
    }
    """
    try:
        result = await page.evaluate(script)
        return dict(result or {})
    except Exception:
        return {}


def _extract_model_variant(request: ProviderRequest) -> str | None:
    if request.metadata and isinstance(request.metadata, dict):
        raw = request.metadata.get("chatgpt_model_variant")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    prompt = request.prompt or ""
    for line in prompt.splitlines():
        line = line.strip()
        if line.startswith("[Model:") and line.endswith("]"):
            inner = line[len("[Model:"): -1].strip()
            if inner:
                return inner
    return None


async def _switch_chatgpt_model(page: Any, variant: str) -> bool:
    import asyncio

    variant_lower = variant.lower().strip()

    model_labels: dict[str, list[str]] = {
        "instant": ["instant", "gpt-4o", "gpt-4o mini", "auto"],
        "thinking": ["thinking", "o3", "o4-mini"],
        "pro": ["pro", "gpt-4.5"],
    }

    labels = model_labels.get(variant_lower, [variant_lower])

    model_picker_selectors = [
        "button[data-testid='model-switcher']",
        "button[aria-label*='model']",
        "button[aria-label*='Model']",
    ]

    for selector in model_picker_selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await asyncio.sleep(0.8)
                break
        except Exception:
            continue
    else:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    for label in labels:
        try:
            script = r"""
    (label) => {
        function visible(el) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
        }
        const nodes = Array.from(document.querySelectorAll(
            'button, [role="option"], [role="menuitem"], [role="radio"], [role="tab"], li, div[role="option"]'
        ));
        for (const el of nodes) {
            if (!visible(el)) continue;
            const txt = ((el.getAttribute('aria-label') || '') + ' ' +
                         (el.getAttribute('title') || '') + ' ' +
                         (el.innerText || '') + ' ' +
                         (el.textContent || '')).toLowerCase();
            if (txt.includes(label.toLowerCase())) {
                el.click();
                return true;
            }
        }
        return false;
    }
            """
            clicked = await page.evaluate(script, label)
            if clicked:
                await asyncio.sleep(0.6)
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                return True
        except Exception:
            continue

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return False
