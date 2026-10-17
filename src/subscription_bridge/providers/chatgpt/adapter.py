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
        # The caller receives an idle browser session; no request is running yet.
        await self._pool.release(session.session_id)
        return session.session_id

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        start = time.monotonic()
        session: TabSession | None = None
        upload_meta: dict[str, Any] | None = None
        prompt = request.prompt

        try:
            session = await self._pool.acquire(
                "chatgpt", request.run_id, self._page_factory,
                allow_cross_run_reuse=not bool((request.metadata or {}).get("isolated_conversation")),
            )

            # OpenCode compacted/rewrote history: the browser chat is stale,
            # start a fresh chat and resend the post-compaction transcript.
            if (request.metadata or {}).get("restart_conversation"):
                session.has_active_conversation = False
                session.selected_model_variant = None
                session.served_model_id = None

            # The catalog model changed (e.g. chatgpt -> chatgpt-thinking). Each
            # model brings its own system prompt, and the browser tab may be
            # reused across models, so restart the transcript instead of appending
            # a foreign system prompt.
            requested_model = str((request.metadata or {}).get("model_id") or "")
            if (
                requested_model
                and session.has_active_conversation
                and session.served_model_id
                and session.served_model_id != requested_model
            ):
                logger.info(
                    "model_change_restart",
                    previous=session.served_model_id,
                    current=requested_model,
                    run_id=request.run_id,
                )
                session.has_active_conversation = False
                session.selected_model_variant = None
                session.served_model_id = requested_model

            # The system/tool instructions are injected once per browser chat.
            if request.system_prompt and not session.has_active_conversation:
                prompt = request.system_prompt + "\n\n" + prompt
            # On a fresh/reset browser chat, restore the full OpenCode transcript;
            # on a continuing browser chat, send only the incremental tail.
            if not session.has_active_conversation and isinstance(request.metadata, dict):
                prompt = str(request.metadata.get("full_prompt") or prompt)
                if request.system_prompt:
                    # full_prompt has no system message; prepend it after the
                    # transcript override so the system instructions survive.
                    prompt = request.system_prompt + "\n\n" + prompt
            if not session.has_active_conversation:
                await self._ensure_fresh_chat(session)
            await _wait_for_composer_ready(session.page)

            requested_variant = _extract_model_variant(request)
            if requested_variant:
                logger.info(
                    "model_switch_requested",
                    requested=requested_variant,
                    run_id=request.run_id,
                )
                switched = await _set_thinking(session.page, requested_variant)
                session.selected_model_variant = requested_variant if switched else None
                logger.info(
                    "model_switch_done",
                    requested=requested_variant,
                    switched=switched,
                    run_id=request.run_id,
                )
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
                    session.has_active_conversation = True
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
        page = session.page
        # Preserve the user's already-open, logged-in ChatGPT tab when it is an
        # empty composer. If it contains an older conversation, start a clean one.
        try:
            current = (page.url or "").lower()
            if ("chatgpt.com" in current or "chat.openai.com" in current) and await _chatgpt_app_ready(page):
                if await _count_assistant_messages(page) == 0:
                    await dismiss_overlays(page)
                    return
        except Exception:
            pass
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
    script = r"""
    (text) => {
        const textareaSel = '#prompt-textarea, textarea[data-testid="prompt-textarea"], ' +
            '[data-testid="composer"] textarea';
        let el = document.querySelector(textareaSel);
        if (el) {
            const tag = (el.tagName || '').toLowerCase();
            if (tag === 'textarea' || tag === 'input') {
                el.value = text;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
        }
        el = document.querySelector(
            '[data-testid="composer"] [contenteditable="true"], ' +
            'div.ProseMirror[contenteditable="true"], ' +
            'main div[contenteditable="true"]'
        );
        if (!el) return false;
        el.focus();
        document.execCommand('selectAll');
        document.execCommand('insertText', false, text);
        return true;
    }
    """
    try:
        inserted = bool(await page.evaluate(script, text))
        if not inserted:
            return False
        await asyncio.sleep(0.2)
        actual = await _get_composer_text(page)
        return actual == text or actual.strip() == text.strip()
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
        if (
            report.get("stopVisible")
            or report.get("thinkingVisible")
            or int(report.get("streamingWords", 0)) > 0
        ):
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
    last_len = -1
    stable_cycles = 0
    # Stream-word spans can linger as DOM artifacts after ChatGPT marks the
    # response complete. If text length is stable long enough, treat as done
    # even if stream words remain.
    stable_with_stream = 0
    while time.monotonic() < deadline:
        report = await _submission_activity_report(page)
        current_count = int(report.get("assistantCount", 0))
        streaming = int(report.get("streamingWords", 0))
        is_generating = (
            bool(report.get("stopVisible"))
            or bool(report.get("progressVisible"))
        )

        target_reached = current_count > pre_send_count
        current_len = int(report.get("lastTextLen", 0))

        if target_reached and current_len > 0:
            if current_len != last_len:
                stable_cycles = 0
                stable_with_stream = 0
            else:
                stable_cycles += 1
                if streaming > 0:
                    stable_with_stream += 1
                # Clean completion: no activity flags, text stable 4s
                if not is_generating and streaming == 0 and stable_cycles >= 8:
                    return True
                # Fallback: text stable 10s even with lingering stream words
                if stable_with_stream >= 20:
                    return True
            last_len = current_len
        else:
            stable_cycles = 0
            stable_with_stream = 0
            last_len = current_len if current_len else last_len

        await asyncio.sleep(0.5)
    return False


async def _extract_latest_assistant_text(page: Any, pre_send_count: int = 0) -> str:
    script = r"""
    () => {
        // Prefer content-bearing selectors. data-conversation-role="assistant"
        // wraps the whole turn including the "ChatGPT said:" label; dig into
        // nested markdown when that is the only match.
        const selectors = [
            '[data-markdown-text-style="assistant-message"]',
            '[class*="DilResponseRoot"]',
            '[data-message-author-role="assistant"]',
            '[data-conversation-role="assistant"]',
        ];

        function visible(el) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }

        // Extract text from a new-UI code block: header is marked
        // data-markdown-copy="exclude" (language label + Run); the .grid
        // sibling holds the actual code and preserves indentation via innerText.
        function codeBlockText(block) {
            const grid = block.querySelector('.grid');
            if (grid) {
                const t = (grid.innerText || '').trim();
                if (t) return t;
            }
            // Fallback: clone block, strip excluded header, take innerText
            const clone = block.cloneNode(true);
            clone.querySelectorAll('[data-markdown-copy="exclude"]').forEach(n => n.remove());
            return (clone.innerText || clone.textContent || '').trim();
        }

        function blockText(root) {
            // New ChatGPT UI: code blocks use [data-code-block="true"] with a
            // .grid content area. Prefer those (innerTex preserves indentation).
            const codeBlocks = Array.from(root.querySelectorAll('[data-code-block="true"]'))
                .filter(visible);
            if (codeBlocks.length) {
                const parts = codeBlocks.map(codeBlockText).filter(Boolean);
                if (parts.length) return parts.join('\n\n');
            }
            // Classic markdown pre/code
            const pres = Array.from(root.querySelectorAll('pre')).filter(visible);
            if (pres.length) {
                const parts = pres.map(p => (p.innerText || p.textContent || '').trim()).filter(Boolean);
                if (parts.length) return parts.join('\n\n');
            }
            // Prose blocks: join with newlines so structure is preserved.
            // textContent alone concatenates <p> siblings with no separator;
            // innerText collapses indentation inside streamed word-spans.
            const blocks = root.querySelectorAll(
                'p, li, h1, h2, h3, h4, h5, h6, blockquote'
            );
            if (blocks.length) {
                const parts = [];
                for (const b of blocks) {
                    if (b.closest('[data-code-block="true"]')) continue;
                    if (b.closest('pre') && b.tagName !== 'PRE') continue;
                    const t = (b.innerText || b.textContent || '').trim();
                    if (t) parts.push(t);
                }
                if (parts.length) return parts.join('\n\n');
            }
            // Fallback: walk top-level text nodes / spans preserving whitespace
            return root.textContent || root.innerText || '';
        }

        for (const sel of selectors) {
            const elements = Array.from(document.querySelectorAll(sel));
            const vis = elements.filter(visible);
            if (!vis.length) continue;
            const lastEl = vis[vis.length - 1];
            // Prefer nested markdown content inside a conversation-role wrapper
            const nested = lastEl.querySelector(
                '[data-markdown-text-style="assistant-message"], [class*="DilResponseRoot"], .markdown, .prose'
            );
            const source = nested || lastEl;
            const text = blockText(source).trim();
            if (text) return text;
        }
        return '';
    }
    """
    try:
        text = await page.evaluate(script)
        if text and str(text).strip():
            return str(text).strip()
    except Exception:
        pass

    for selector in [".markdown", ".prose", '[class*="MarkdownRoot"]']:
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
        const pre = lastEl.querySelector('pre');
        if (pre) {
            const codeText = (pre.innerText || pre.textContent || '').trim();
            if (codeText) return codeText;
        }
        return lastEl.textContent || lastEl.innerText || '';
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
        // New ChatGPT UI: assistant messages use data-conversation-role or
        // data-markdown-text-style. Legacy UI used data-message-author-role.
        const assistantSelectors = [
            '[data-conversation-role="assistant"]',
            '[data-markdown-text-style="assistant-message"]',
            '[class*="DilResponseRoot"]',
            '[data-message-author-role="assistant"]',
        ];
        let assistantEls = [];
        for (const sel of assistantSelectors) {
            assistantEls = Array.from(document.querySelectorAll(sel)).filter(visible);
            if (assistantEls.length) break;
        }
        // Streaming word spans mean the model is still writing.
        // Scope to the LATEST assistant message only — leftover stream words
        // from a prior stalled response must not block completion detection.
        let streamingWords = 0;
        let lastTextLen = 0;
        if (assistantEls.length) {
            const lastEl = assistantEls[assistantEls.length - 1];
            streamingWords = lastEl.querySelectorAll('[data-d-stream-word]').length;
            lastTextLen = (lastEl.textContent || '').length;
        }
        // Turn-state: incomplete means generation still running
        const incompleteTurns = Array.from(document.querySelectorAll(
            '[data-talvt-turn-state="generating"],' +
            ' [data-talvt-turn-state="thinking"],' +
            ' [data-talvt-turn-state="streaming"]'
        )).filter(visible);
        const stopButton = document.querySelector(
            'button[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="stop"]'
        );
        return {
            // Stop button / incomplete turns only — streamingWords is reported
            // separately so the wait loop can distinguish active streaming from
            // lingering DOM artifacts after ChatGPT marks the response complete.
            stopVisible: stopVisible || visible(stopButton) || incompleteTurns.length > 0,
            thinkingVisible,
            progressVisible,
            assistantCount: assistantEls.length,
            streamingWords,
            lastTextLen,
        };
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


_THINK_ON_VARIANTS = {"thinking", "think", "pro", "reason", "reasoning"}
_THINK_OFF_VARIANTS = {"instant", "fast", "auto", "default", "gpt-4o", "gpt-4o mini"}


def _variant_wants_thinking(variant: str) -> bool:
    v = variant.strip().lower()
    if v in _THINK_OFF_VARIANTS:
        return False
    return v in _THINK_ON_VARIANTS


async def _set_thinking(page: Any, variant: str) -> bool:
    try:
        loc = page.locator("button:has-text('Think')").first
        if await loc.count() == 0:
            return False
        wanted = _variant_wants_thinking(variant)
        pressed = await loc.get_attribute("aria-pressed") == "true"
        if pressed != wanted:
            await loc.click()
            await asyncio.sleep(0.4)
        return True
    except Exception:
        return False
