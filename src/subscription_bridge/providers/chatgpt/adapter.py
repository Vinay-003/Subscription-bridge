from __future__ import annotations

import asyncio
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

        try:
            session = await self._pool.acquire("chatgpt", request.run_id, self._page_factory)

            if request.system_prompt:
                prompt = request.system_prompt + "\n\n" + prompt

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

            await self._ensure_fresh_chat(session)
            await _wait_for_composer_ready(session.page)
            pre_send_count = await _count_assistant_messages(session.page)

            ok = await _type_prompt(session.page, prompt)
            if not ok:
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Failed to type prompt into ChatGPT composer",
                    metadata=upload_meta or {},
                )

            await _submit_via_enter(session.page)
            logger.info("send_method_used", method="enter", run_id=request.run_id)

            accepted = await _wait_for_send_confirmation(
                session.page, pre_send_count=pre_send_count, timeout=20.0,
            )
            if not accepted:
                await _click_send_button(session.page)
                accepted = await _wait_for_send_confirmation(
                    session.page, pre_send_count=pre_send_count, timeout=25.0,
                )

            if not accepted:
                await session.screenshot_debug("send_not_confirmed")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="ChatGPT did not confirm prompt submission",
                    metadata=upload_meta or {},
                )

            complete = await _wait_for_response_complete(
                session.page, pre_send_count=pre_send_count, timeout=180.0,
            )
            if not complete:
                await session.screenshot_debug("response_timeout")
                text = await _extract_latest_assistant_text(session.page, pre_send_count)
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

            text = await _extract_latest_assistant_text(session.page, pre_send_count)
            if not text:
                await session.screenshot_debug("empty_response")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="ChatGPT returned empty response",
                    metadata=upload_meta or {},
                )

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
        page = session.page
        await page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(0.5)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            ready = await _chatgpt_app_ready(page)
            if ready:
                await dismiss_overlays(page)
                return
            await asyncio.sleep(0.5)
        raise RuntimeError("ChatGPT app failed to become ready within 20s")


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


async def _wait_for_composer_ready(page: Any) -> None:
    await _find_composer(page, timeout=30)


async def _type_prompt(page: Any, text: str) -> bool:
    composer = await _find_composer(page)
    await composer.scroll_into_view_if_needed(timeout=5000)

    # Method 1: JavaScript paste (fast, handles long text)
    ok = await _paste_via_js(page, composer, text)
    if ok:
        await asyncio.sleep(0.3)
        return True

    # Method 2: keyboard fallback
    try:
        await composer.click(timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(0.15)
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.25)
    await page.keyboard.insert_text(text)
    await asyncio.sleep(0.3)
    actual = await _get_composer_text(page)
    if actual and len(actual.strip()) > 20:
        return True
    return bool(actual and actual.strip())


async def _paste_via_js(page: Any, composer: Any, text: str) -> bool:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("</script>", "<\\/script>")
    script = rf"""
    () => {{
        // Try textarea first
        const textareaSel = '#prompt-textarea, textarea[data-testid="prompt-textarea"], ' +
            '[data-testid="composer"] textarea';
        let el = document.querySelector(textareaSel);
        if (el) {{
            const tag = (el.tagName || '').toLowerCase();
            if (tag === 'textarea' || tag === 'input') {{
                el.value = '{escaped}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            }}
        }}
        // Try contenteditable (ProseMirror)
        el = document.querySelector(
            '[data-testid="composer"] [contenteditable="true"], ' +
            'div.ProseMirror[contenteditable="true"], ' +
            'main div[contenteditable="true"]'
        );
        if (!el) return false;
        el.focus();
        document.execCommand('selectAll');
        document.execCommand('insertText', false, '{escaped}');
        return true;
    }}
    """
    try:
        return bool(await page.evaluate(script))
    except Exception:
        return False


async def _submit_via_enter(page: Any) -> None:
    try:
        composer = await _find_composer(page, timeout=5)
        await composer.focus()
        await composer.click()
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


async def _count_assistant_messages(page: Any) -> int:
    report = await _submission_activity_report(page)
    return int(report.get("assistantCount", 0))


async def _wait_for_send_confirmation(
    page: Any, timeout: float = 20.0, pre_send_count: int = 0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        composer_text = await _get_composer_text(page)
        if not composer_text.strip():
            return True
        report = await _submission_activity_report(page)
        if report.get("stopVisible") or report.get("thinkingVisible"):
            return True
        current_count = int(report.get("assistantCount", 0))
        if current_count > pre_send_count:
            return True
        await asyncio.sleep(0.5)
    return False


async def _wait_for_response_complete(
    page: Any, timeout: float = 180.0, pre_send_count: int = 0,
) -> bool:
    deadline = time.monotonic() + timeout
    last_count = 0
    stable_cycles = 0
    while time.monotonic() < deadline:
        report = await _submission_activity_report(page)
        current_count = int(report.get("assistantCount", 0))
        is_generating = report.get("stopVisible") or report.get("progressVisible")

        target_reached = current_count > pre_send_count

        if not is_generating and target_reached:
            if current_count != last_count:
                stable_cycles = 0
            else:
                stable_cycles += 1
                if stable_cycles >= 8:
                    return True
            last_count = current_count
        else:
            stable_cycles = 0
            if not target_reached:
                last_count = current_count

        await asyncio.sleep(0.5)
    return False


async def _extract_latest_assistant_text(page: Any, pre_send_count: int = 0) -> str:
    script = r"""
    () => {
        const elements = Array.from(document.querySelectorAll(
            '[data-message-author-role="assistant"]'
        ));
        const visible = elements.filter(el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        });
        if (!visible.length) return '';
        const lastEl = visible[visible.length - 1];
        return lastEl.innerText || lastEl.textContent || '';
    }
    """
    try:
        text = await page.evaluate(script)
        if text and str(text).strip():
            return str(text).strip()
    except Exception:
        pass

    for selector in [".markdown", ".prose"]:
        try:
            text = await page.evaluate(
                r"""
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
                """,
                selector,
            )
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
