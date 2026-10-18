from __future__ import annotations

import asyncio
import time
from typing import Any

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.browser.tab_session import TabSession
from subscription_bridge.browser.ui_guard import (
    collect_button_diagnostics,
    dismiss_overlays,
    safe_click_labels,
)
from subscription_bridge.logging.logger import get_logger
from subscription_bridge.providers.base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderRequest,
    ProviderResponse,
)
from subscription_bridge.providers.gemini.attachments import (
    load_upload_config,
    validate_attachments,
)
from subscription_bridge.providers.gemini.health import (
    check_gemini_ready,
    check_provider_health,
    navigate_to_fresh_chat,
)
from subscription_bridge.providers.gemini.prompt_io import (
    find_composer,
    set_prompt_text,
)
from subscription_bridge.providers.gemini.response_reader import (
    extract_latest_assistant_text,
    submission_activity_report,
    wait_for_response_complete,
    wait_for_send_confirmation,
)
from subscription_bridge.providers.gemini.selectors import get_selector
from subscription_bridge.providers.gemini.upload import UploadError, upload_files
from subscription_bridge.providers.timeouts import response_wait_seconds, send_confirm_seconds


class GeminiError(Exception):
    ...


_UI_ERROR_MARKERS = (
    "sorry, something went wrong",
    "please try your request again",
    "please try again later",
    "couldn't load response",
)


def _is_ui_error_text(text: str) -> bool:
    """Detect Gemini's own failure banners so they are never shipped as answers."""
    normalized = " ".join(text.lower().split())
    if len(normalized) > 600:
        return False
    return any(marker in normalized for marker in _UI_ERROR_MARKERS)


class GeminiProviderAdapter(ProviderAdapter):
    name = "gemini"
    capabilities: set[ProviderCapability] = {"text_chat", "code_reasoning", "file_upload", "vision"}

    def __init__(self, session_pool: SessionPool, page_factory: Any) -> None:
        self._pool = session_pool
        self._page_factory = page_factory

    async def create_session(self) -> str:
        session = await self._pool.acquire("gemini", "", self._page_factory)
        # The caller receives an idle browser session; no request is running yet.
        await self._pool.release(session.session_id)
        return session.session_id

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        start = time.monotonic()
        session: TabSession | None = None
        upload_meta: dict[str, Any] | None = None
        prompt = request.prompt
        logger = get_logger("provider.gemini")

        try:
            session = await self._pool.acquire(
                "gemini", request.run_id, self._page_factory,
                allow_cross_run_reuse=not bool((request.metadata or {}).get("isolated_conversation")),
            )

            # OpenCode compacted/rewrote history: the browser chat is stale,
            # start a fresh chat and resend the post-compaction transcript.
            if (request.metadata or {}).get("restart_conversation"):
                session.has_active_conversation = False
                session.selected_model_variant = None
                session.thinking_level = None
                session.served_model_id = None

            # The catalog model changed (e.g. flash -> pro). Each model brings its
            # own system prompt, and the browser tab may be reused across models,
            # so restart the transcript instead of appending a foreign system prompt.
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
                session.thinking_level = None
                session.served_model_id = requested_model

            # On a fresh/reset browser chat, restore the full OpenCode transcript;
            # on a continuing browser chat, send only the incremental tail.
            if not session.has_active_conversation and isinstance(request.metadata, dict):
                prompt = str(request.metadata.get("full_prompt") or prompt)
            # The system/tool instructions are injected once per browser chat.
            if request.system_prompt and not session.has_active_conversation:
                prompt = request.system_prompt + "\n\n" + prompt

            # A freshly claimed CDP tab (or restored Chrome tab) may still be
            # hydrating; model/thinking controls only exist once the app shell
            # is interactive. Wait here so switches do not silently no-op.
            await _wait_for_ui_ready(session.page)

            requested_variant = _extract_model_variant(request)
            requested_thinking = _extract_thinking_enabled(request)
            requested_level = _extract_thinking_level(request)

            if requested_variant and session.selected_model_variant != requested_variant:
                detected_before = await _detect_model_label(session.page)
                logger.info(
                    "model_switch_requested",
                    requested=requested_variant,
                    thinking=requested_thinking,
                    detected_before=detected_before,
                    run_id=request.run_id,
                )
                switched = await _switch_model_variant(session.page, requested_variant)
                detected_after = await _detect_model_label(session.page)
                if switched:
                    session.selected_model_variant = requested_variant
                    logger.info(
                        "model_switch_done",
                        requested=requested_variant,
                        detected_before=detected_before,
                        detected_after=detected_after,
                        run_id=request.run_id,
                    )
                else:
                    diagnostics = await collect_button_diagnostics(session.page)
                    logger.warning(
                        "model_switch_failed",
                        requested=requested_variant,
                        detected_before=detected_before,
                        detected_after=detected_after,
                        diagnostics=diagnostics,
                        run_id=request.run_id,
                    )

            if requested_level and session.thinking_level != requested_level:
                logger.info(
                    "thinking_level_requested",
                    level=requested_level,
                    run_id=request.run_id,
                )
                applied = await _set_thinking_level(session.page, requested_level)
                session.thinking_level = requested_level if applied else None
                logger.info(
                    "thinking_level_done",
                    level=requested_level,
                    applied=applied,
                    run_id=request.run_id,
                )
            elif requested_thinking and not requested_level:
                await _toggle_thinking(session.page, enabled=True)

            is_continuation = session.has_active_conversation

            if not is_continuation:
                await self._ensure_fresh_chat(session)
                if request.attachments:
                    upload_meta = await self._handle_attachments(session, request.attachments, start)
                    if upload_meta.get("upload_method") == "text_inline":
                        preamble_parts = []
                        for i, fname in enumerate(upload_meta.get("inline_text_attachments", [])):
                            content = upload_meta.get("inline_text_contents", [{}])[i].get("content", "")
                            if content:
                                preamble_parts.append(f"[File: {fname}]\n```\n{content}\n```")
                        if preamble_parts:
                            prompt = "\n\n".join(preamble_parts) + "\n\n" + prompt
            else:
                upload_meta = {}

            # Tool-call output format is fully specified by the sentinel protocol
            # in the system prompt; do not append a contradictory JSON directive.

            await find_composer(session.page)
            pre_send_report = await submission_activity_report(session.page)
            pre_send_count = int(pre_send_report.get("assistantCount", 0))
            await set_prompt_text(session.page, prompt)

            from subscription_bridge.providers.gemini.prompt_io import submit_via_enter
            await submit_via_enter(session.page)
            logger.info("send_method_used", method="enter", run_id=request.run_id)

            confirm_wait = send_confirm_seconds("gemini")
            accepted = await wait_for_send_confirmation(
                session.page, timeout=round(confirm_wait * 0.6, 1), pre_send_count=pre_send_count
            )
            if not accepted:
                logger.info("send_method_fallback", method="send_button_click", run_id=request.run_id)
                await _click_send_button(session.page)
                accepted = await wait_for_send_confirmation(
                    session.page, timeout=confirm_wait, pre_send_count=pre_send_count
                )

            if not accepted:
                await session.screenshot_debug("send_not_confirmed")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini did not confirm prompt submission",
                    metadata=upload_meta or {},
                )

            response_wait = response_wait_seconds("gemini", request.timeout_seconds)
            logger.info(
                "response_wait_budget",
                seconds=response_wait,
                requested=request.timeout_seconds,
                run_id=request.run_id,
            )
            complete = await wait_for_response_complete(
                session.page, timeout=response_wait, pre_send_count=pre_send_count
            )
            if not complete:
                await session.screenshot_debug("response_timeout")
                text = await extract_latest_assistant_text(session.page)
                if text and _is_ui_error_text(text):
                    await session.screenshot_debug("error_response")
                    session.has_active_conversation = True
                    return ProviderResponse(
                        provider=self.name, text="", raw_text=text, success=False,
                        latency_seconds=time.monotonic() - start,
                        error=f"Gemini returned an error response: {text[:300]}",
                        metadata=upload_meta or {},
                    )
                if text:
                    return ProviderResponse(
                        provider=self.name, text=text, raw_text=text, success=True,
                        latency_seconds=time.monotonic() - start,
                        metadata=upload_meta or {},
                    )
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini did not produce a response within timeout",
                    metadata=upload_meta or {},
                )

            text = await extract_latest_assistant_text(session.page)
            if not text:
                await session.screenshot_debug("empty_response")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini returned empty response",
                    metadata=upload_meta or {},
                )
            if _is_ui_error_text(text):
                await session.screenshot_debug("error_response")
                session.has_active_conversation = True
                return ProviderResponse(
                    provider=self.name, text="", raw_text=text, success=False,
                    latency_seconds=time.monotonic() - start,
                    error=f"Gemini returned an error response: {text[:300]}",
                    metadata=upload_meta or {},
                )

            detected_after = await _detect_model_label(session.page)
            logger.info(
                "model_used",
                requested=requested_variant,
                detected_after=detected_after,
                run_id=request.run_id,
            )

            session.has_active_conversation = True

            return ProviderResponse(
                provider=self.name, text=text, raw_text=text, success=True,
                latency_seconds=time.monotonic() - start,
                metadata={
                    **(upload_meta or {}),
                    "requested_model": requested_variant or "",
                    "detected_model": detected_after,
                },
            )

        except (UploadError, ValueError) as e:
            if session is not None:
                await session.screenshot_debug("upload_error")
            return ProviderResponse(
                provider=self.name, text="", raw_text="", success=False,
                latency_seconds=time.monotonic() - start,
                error=str(e), metadata=upload_meta or {},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if session is not None:
                await session.screenshot_debug("provider_error")
            return ProviderResponse(
                provider=self.name, text="", raw_text="", success=False,
                latency_seconds=time.monotonic() - start,
                error=f"Gemini provider error: {e}", metadata=upload_meta or {},
            )
        finally:
            if session is not None:
                await self._pool.release(session.session_id)

    async def _handle_attachments(
        self,
        session: TabSession,
        attachment_paths: list[str],
        start: float,
    ) -> dict[str, Any]:
        config = load_upload_config()
        validated = validate_attachments(attachment_paths, config)

        upload_start = time.monotonic()
        result = await upload_files(session.page, validated, config)
        upload_duration = time.monotonic() - upload_start

        meta: dict[str, Any] = {
            "attachment_count": len(validated),
            "attachment_names": [a.filename for a in validated],
            "attachment_types": [a.extension for a in validated],
            "attachment_categories": [a.category for a in validated],
            "attachment_mime_types": [a.mime_type for a in validated],
            "attachment_sizes": [a.size_bytes for a in validated],
            "total_attachment_bytes": sum(a.size_bytes for a in validated),
            "upload_duration_seconds": round(upload_duration, 2),
            "upload_method": result.get("method", "unknown"),
            "prompt_length": 0,
        }
        if result.get("method") == "text_inline":
            texts = result.get("text_contents", [])
            meta["inline_text_attachments"] = [t["filename"] for t in texts]
            meta["inline_text_contents"] = [t["content"] for t in texts]
        return meta

    async def reset_chat(self, session_id: str) -> None:
        if session_id == "all":
            for s in self._pool.list_sessions():
                sid = s["session_id"]
                session_obj = self._pool.get_session(sid)
                if session_obj is not None and session_obj.provider_name == "gemini":
                    await self._pool.reset(sid)
        else:
            await self._pool.reset(session_id)

    async def health_check(self) -> bool:
        try:
            session = await self._pool.acquire("gemini", "health-check", self._page_factory)
            try:
                await navigate_to_fresh_chat(session.page)
                health = await check_gemini_ready(session.page)
                raw = health.get("ready", False)
                return bool(raw)
            finally:
                await self._pool.release(session.session_id)
        except Exception:
            return False

    async def close_session(self, session_id: str) -> None:
        await self._pool.close(session_id)

    async def _ensure_fresh_chat(self, session: TabSession) -> None:
        await navigate_to_fresh_chat(session.page)
        import time as _time
        deadline = _time.monotonic() + 60.0
        while _time.monotonic() < deadline:
            health = await check_gemini_ready(session.page)
            if health.get("temporary_chat"):
                raise GeminiError("Gemini is in Temporary Chat mode")
            if health.get("ready"):
                return
            if health.get("needs_login"):
                detail = health.get("needs_login_detail", "")
                raise GeminiError(
                    f"User must log in to Gemini first. {detail}".strip()
                )
            await _async_sleep(1.0)
        raise GeminiError(
            "Timed out waiting for Gemini readiness. "
            "Open Chrome, navigate to gemini.google.com, log in, and try again."
        )

    async def detailed_health(self) -> dict[str, Any]:
        session = await self._pool.acquire("gemini", "detailed-health", self._page_factory)
        try:
            await navigate_to_fresh_chat(session.page)
            return await check_provider_health(session.page)
        finally:
            await self._pool.release(session.session_id)


async def _click_send_button(page: Any) -> bool:
    from subscription_bridge.providers.gemini.selectors import get_selector
    send_selectors = get_selector("buttons.send")
    for selector in send_selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                return True
        except Exception:
            continue
    return False


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


def _extract_model_variant(request: ProviderRequest) -> str | None:
    if request.metadata and isinstance(request.metadata, dict):
        raw = request.metadata.get("gemini_model_variant")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()

    prompt = request.prompt or ""
    for line in prompt.splitlines():
        line = line.strip()
        if line.startswith("[Model:") and line.endswith("]"):
            inner = line[len("[Model:") : -1].strip()
            if inner:
                return inner
    return None


def _extract_thinking_enabled(request: ProviderRequest) -> bool:
    if request.metadata and isinstance(request.metadata, dict):
        raw = request.metadata.get("gemini_thinking")
        if isinstance(raw, bool):
            return raw
    return False


def _extract_thinking_level(request: ProviderRequest) -> str | None:
    """Read the requested Gemini thinking level (low/medium/high)."""
    if not (request.metadata and isinstance(request.metadata, dict)):
        return None
    raw = request.metadata.get("thinking_level") or request.metadata.get("gemini_thinking_level")
    if not isinstance(raw, str):
        return None
    level = raw.strip().lower()
    if level in ("low", "medium", "high"):
        return level
    if level in ("none", "minimal"):
        return "low"
    if level in ("xhigh", "max"):
        return "high"
    return None


def _normalize_variant(name: str) -> str:
    return " ".join(name.lower().split())


def _variant_aliases(name: str) -> list[str]:
    n = _normalize_variant(name)
    if "argon" in n:
        return ["argon"]
    if "lite" in n or "flash lite" in n or "flash-lite" in n:
        return ["flash-lite"]
    if "flash" in n:
        return ["flash"]
    if "thinking" in n or "deep think" in n:
        return ["pro"]
    if "pro" in n:
        return ["pro"]
    return [n]


def _variant_select_labels(name: str) -> list[str]:
    # Exact (normalized) name first so "3.8 Flash" never matches
    # "3.5 Flash-Lite", which also contains the substring "flash".
    n = _normalize_variant(name)
    labels = [n]

    def add(*candidates: str) -> None:
        for candidate in candidates:
            if candidate not in labels:
                labels.append(candidate)

    if "argon" in n:
        add("4 argon", "argon", "complex tasks")
    elif "lite" in n or "flash lite" in n or "flash-lite" in n:
        add("3.5 flash-lite", "flash-lite", "flash lite", "fastest answers")
    elif "thinking" in n or "deep think" in n:
        add("3.1 pro", "pro", "advanced reasoning")
    elif "flash" in n:
        add("3.8 flash", "flash", "all-around help")
    elif "pro" in n:
        add("3.1 pro", "pro", "advanced reasoning")
    return labels


async def _switch_model_variant(page: Any, variant: str) -> bool:
    if not variant:
        return False

    select_labels = _variant_select_labels(variant)

    try:
        loc = page.locator("button[aria-label^='Open mode picker']").first
        if await loc.count() > 0 and await loc.is_visible():
            await loc.click()
            await _async_sleep(0.8)
            if await _click_and_verify_model(page, variant, select_labels):
                return True
    except Exception:
        pass

    open_labels = ["open mode picker", "mode picker", "model", "gemini"]
    for _ in range(2):
        opened = await safe_click_labels(page, open_labels, timeout=4)
        if opened:
            await _async_sleep(0.8)
            if await _click_and_verify_model(page, variant, select_labels):
                return True
        await _async_sleep(0.4)

    for _ in range(2):
        for selector in get_selector("model_toggle"):
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await _async_sleep(0.8)
                    if await _click_and_verify_model(page, variant, select_labels):
                        return True
                    break
            except Exception:
                continue
        await _async_sleep(0.4)

    return False


async def _click_and_verify_model(page: Any, variant: str, select_labels: list[str]) -> bool:
    """Click a model in the open picker, then verify the picker selection."""
    clicked = await _click_model_in_overlay(page, select_labels)
    await _async_sleep(0.6)
    await dismiss_overlays(page)
    if not clicked:
        return False
    selected = await _read_selected_model_label(page)
    if selected is None:
        # Could not re-open the picker to verify; keep the optimistic result.
        return True
    return _variant_label_matches(variant, selected)


def _variant_label_matches(variant: str, selected: str) -> bool:
    """Match variant vs the picker's selected label by model identity."""
    wanted = set(_variant_aliases(variant))
    actual = set(_variant_aliases(selected))
    return bool(wanted & actual)


async def _read_selected_model_label(page: Any) -> str | None:
    if not await _open_mode_picker(page):
        return None
    label: str | None = None
    try:
        raw = await page.evaluate(
            """() => {
                const menus = document.querySelectorAll('gem-menu[data-test-id="gem-mode-menu"]');
                for (const menu of menus) {
                    const r = menu.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    for (const item of menu.querySelectorAll('gem-menu-item[data-test-id^="bard-mode-option-"]')) {
                        if (!item.className.includes('selected')) continue;
                        const l = item.querySelector('.label');
                        return l ? l.innerText.trim() : null;
                    }
                }
                return null;
            }"""
        )
        label = raw if isinstance(raw, str) and raw.strip() else None
    except Exception:
        label = None
    finally:
        await dismiss_overlays(page)
    return label


_MODE_PICKER_SELECTORS = (
    "button[aria-label^='Open mode picker']",
    "button[aria-label='Open mode picker']",
)


async def _mode_picker_visible(page: Any) -> bool:
    """True when the toolbar's mode picker button is rendered and visible."""
    for selector in _MODE_PICKER_SELECTORS:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def _wait_for_ui_ready(
    page: Any,
    timeout_seconds: float = 30.0,
    login_grace_seconds: float = 10.0,
) -> bool:
    """Wait for the Gemini app shell to hydrate before touching its controls.

    A freshly claimed CDP tab (or a just-restored Chrome tab) renders its DOM
    progressively: the composer, mode picker and thinking submenu only exist
    once the app shell is interactive. Without this wait, model switches
    silently no-op on cold pages. ``needs_login`` is only terminal once it
    persists for ``login_grace_seconds``, so a still-hydrating page is not
    misread as logged out.
    """
    deadline = time.monotonic() + timeout_seconds
    login_since: float | None = None
    while time.monotonic() < deadline:
        try:
            health = await check_gemini_ready(page)
        except Exception:
            health = {}
        if health.get("ready") and await _mode_picker_visible(page):
            return True
        if health.get("needs_login"):
            if login_since is None:
                login_since = time.monotonic()
            if time.monotonic() - login_since >= login_grace_seconds:
                return False
        else:
            login_since = None
        await _async_sleep(0.5)
    return False


async def _open_mode_picker(page: Any) -> bool:
    """Open the Gemini model/mode picker menu."""
    for selector in _MODE_PICKER_SELECTORS:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await _async_sleep(0.8)
                return True
        except Exception:
            continue
    if await safe_click_labels(page, ["open mode picker", "mode picker"], timeout=4):
        await _async_sleep(0.8)
        return True
    for selector in get_selector("model_toggle"):
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await _async_sleep(0.8)
                return True
        except Exception:
            continue
    return False


_THINKING_LEVEL_LABELS = {"low": "Low", "medium": "Medium", "high": "High"}


async def _set_thinking_level(page: Any, level: str) -> bool:
    """Set the Gemini thinking level via the picker's Thinking level submenu."""
    target = _THINKING_LEVEL_LABELS.get(level)
    if not target:
        return False

    if not await _open_mode_picker(page):
        return False

    opened = await page.evaluate(
        """() => {
            const menus = Array.from(document.querySelectorAll('gem-menu[data-test-id="gem-mode-menu"]'));
            for (const menu of menus) {
                const r = menu.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                for (const item of menu.querySelectorAll('gem-menu-item')) {
                    const label = item.querySelector('.label');
                    if (label && label.innerText.trim() === 'Thinking level') {
                        item.click();
                        return true;
                    }
                }
            }
            return false;
        }"""
    )
    if not opened:
        # Fallback: the row may not live under the test-id menu anymore.
        opened = await page.evaluate(
            """() => {
                const items = Array.from(document.querySelectorAll('gem-menu-item'));
                for (const item of items) {
                    const label = item.querySelector('.label');
                    if (!label || label.innerText.trim() !== 'Thinking level') continue;
                    const r = item.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    item.click();
                    return true;
                }
                return false;
            }"""
        )
    if not opened:
        await dismiss_overlays(page)
        return False
    await _async_sleep(0.6)

    result = await page.evaluate(
        """(target) => {
            const containers = Array.from(document.querySelectorAll('.submenu-container, [role="menu"]'));
            for (const container of containers) {
                const r = container.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                for (const item of container.querySelectorAll('gem-menu-item')) {
                    const label = item.querySelector('.label');
                    if (!label || label.innerText.trim() !== target) continue;
                    const checked = item.className.includes('selected') ||
                        !!item.querySelector('gem-icon[aria-label="Selected"]') ||
                        !!item.querySelector('mat-icon[data-mat-icon-name="check"]');
                    if (checked) return 'already';
                    item.click();
                    return 'clicked';
                }
            }
            return 'not_found';
        }""",
        target,
    )
    await _async_sleep(0.6)
    await dismiss_overlays(page)
    return result in ("already", "clicked")


async def _click_model_in_overlay(page: Any, labels: list[str]) -> bool:
    labels_json = str(labels)
    script = f"""
    (function() {{
        const labels = {labels_json};

        function norm(s) {{
            return (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
        }}

        const containers = Array.from(document.querySelectorAll(
            '[role="dialog"], .cdk-overlay-pane, .cdk-overlay-container, [role="menu"], [role="listbox"], gem-menu'
        ));
        const candidates = [];
        const seen = new Set();
        for (const container of containers) {{
            const r = container.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            const items = container.querySelectorAll(
                'button, [role="menuitem"], [role="option"], [role="menuitemradio"], ' +
                '[role="radio"], label, [class*="option"], gem-menu-item'
            );
            for (const el of items) {{
                if (seen.has(el)) continue;
                seen.add(el);
                const cr = el.getBoundingClientRect();
                if (cr.width === 0 || cr.height === 0) continue;
                const nameEl = el.querySelector('.label');
                const name = norm(nameEl ? nameEl.innerText : '');
                const txt = norm((el.getAttribute('aria-label') || '') + ' ' +
                    (el.getAttribute('title') || '') + ' ' +
                    (el.innerText || ''));
                candidates.push({{el: el, name: name, txt: txt}});
            }}
        }}

        // Pass 1: exact name match (prevents "flash" from matching "Flash-Lite").
        for (const label of labels) {{
            for (const candidate of candidates) {{
                if (candidate.name && candidate.name === label) {{
                    candidate.el.scrollIntoView({{block:'center'}});
                    candidate.el.click();
                    return true;
                }}
            }}
        }}

        // Pass 2: substring fallback for older/re-worded UIs.
        for (const candidate of candidates) {{
            for (const label of labels) {{
                if (label && candidate.txt.includes(label)) {{
                    candidate.el.scrollIntoView({{block:'center'}});
                    candidate.el.click();
                    return true;
                }}
            }}
        }}
        return false;
    }})()
    """
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            result = await page.evaluate(script)
            if result:
                return True
            await asyncio.sleep(0.3)
    except Exception:
        pass
    return False


async def _toggle_thinking(page: Any, enabled: bool = True) -> bool:
    script = r"""
    (enabled) => {
        function visible(el) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
        }
        const nodes = Array.from(document.querySelectorAll(
            'button, [role="switch"], [role="checkbox"], [role="button"], label, [class*="toggle"]'
        ));
        for (const el of nodes) {
            if (!visible(el)) continue;
            const txt = ((el.getAttribute('aria-label') || '') + ' ' +
                         (el.getAttribute('title') || '') + ' ' +
                         (el.innerText || '') + ' ' +
                         (el.textContent || '') + ' ' +
                         (el.getAttribute('data-testid') || '')).toLowerCase();
            const isThinking = txt.includes('thinking') || txt.includes('think');
            if (!isThinking) continue;
            const isToggle = el.tagName === 'BUTTON' || el.tagName === 'LABEL' ||
                             el.getAttribute('role') === 'switch' ||
                             el.getAttribute('role') === 'checkbox' ||
                             el.getAttribute('role') === 'button' ||
                             el.classList.contains('toggle');
            if (!isToggle) continue;
            const isChecked = el.getAttribute('aria-checked') === 'true' ||
                              el.classList.contains('active') ||
                              el.classList.contains('selected') ||
                              el.getAttribute('data-state') === 'on';
            if (enabled && !isChecked) { el.click(); return true; }
            if (!enabled && isChecked) { el.click(); return true; }
            return false;
        }
        return false;
    }
    """
    try:
        return bool(await page.evaluate(script, enabled))
    except Exception:
        return False


async def _detect_model_label(page: Any) -> str:
    script = r"""
    () => {
        function visible(el) {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
        }
        const nodes = Array.from(document.querySelectorAll('header button, main button, [role="button"]'));
        for (const n of nodes) {
            if (!visible(n)) continue;
            const txt = ((n.getAttribute('aria-label') || '') + ' ' +
                (n.getAttribute('title') || '') + ' ' +
                (n.innerText || '') + ' ' + (n.textContent || '')).replace(/\s+/g, ' ').trim();
            if (!txt) continue;
            if (/(gemini|flash|pro|think)/i.test(txt)) {
                return txt.slice(0, 120);
            }
        }
        return '';
    }
    """
    try:
        return str(await page.evaluate(script) or "")
    except Exception:
        return ""
