from __future__ import annotations

import time
from typing import Any

from subscription_bridge.providers.gemini.selectors import get_selector


async def submission_activity_report(page: Any) -> dict[str, Any]:
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
        const bodyText = (root.innerText || document.body.innerText || '').replace(/\s+/g, ' ').toLowerCase();
        const buttons = Array.from(document.querySelectorAll('button, [role="button"]')).filter(visible);
        const buttonText = buttons.map(textOf).join(' | ');
        const stopVisible = buttonText.includes('stop response') ||
            buttonText.includes('cancel generation') ||
            buttonText.includes('stop generating');
        const thinkingVisible = bodyText.includes('show thinking') ||
            bodyText.includes('thinking') ||
            bodyText.includes('creating image') ||
            bodyText.includes('generating');
        let progressVisible = false;
        for (const el of document.querySelectorAll(
            '[role="progressbar"], mat-progress-spinner, mat-progress-bar, ' +
            '.spinner, .loading, .progress'
        )) {
            if (visible(el)) { progressVisible = true; break; }
        }
        const responseSelectors = [
            'model-response', '.model-response', '.response-container',
            '[data-response-index]', '[data-chunk-index]',
            '[data-testid*="response"]', '[class*="response"]'
        ];
        let assistantCount = 0;
        for (const sel of responseSelectors) {
            for (const el of document.querySelectorAll(sel)) {
                if (visible(el)) assistantCount++;
            }
        }
        const path = window.location.pathname || '';
        const conversationUrl = /^\/app\//.test(path);
        return {stopVisible, thinkingVisible, progressVisible, assistantCount, conversationUrl, path};
    }
    """
    try:
        result = await page.evaluate(script)
        return dict(result or {})
    except Exception:
        return {}


async def generation_in_progress(page: Any) -> bool:
    report = await submission_activity_report(page)
    return bool(report.get("stopVisible") or report.get("thinkingVisible") or report.get("progressVisible"))


async def wait_for_send_confirmation(
    page: Any,
    timeout: float = 35.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        report = await submission_activity_report(page)
        if report.get("stopVisible") or report.get("thinkingVisible") or report.get("progressVisible"):
            return True
        if report.get("assistantCount", 0) > 0:
            return True
        if report.get("conversationUrl"):
            return True
        composer_empty = await _composer_is_empty(page)
        if composer_empty:
            return True
        await _sleep(0.5)
    return False


async def wait_for_response_complete(
    page: Any,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
) -> bool:
    deadline = time.monotonic() + timeout
    last_count = 0
    stable_cycles = 0
    while time.monotonic() < deadline:
        report = await submission_activity_report(page)
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

        await _sleep(poll_interval)
    return False


async def extract_latest_assistant_text(page: Any) -> str:
    response_selectors = get_selector("response")
    for selector in response_selectors:
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
        if (lastEl.closest('.processing-state_container, [class*="processing-state"]')) {
            return '';
        }
        return lastEl.innerText || lastEl.textContent || '';
    }
            """
            text = await page.evaluate(script, selector)
            if text and str(text).strip():
                return _clean_assistant_text(str(text))
        except Exception:
            continue
    return ""


def _clean_assistant_text(text: str) -> str:
    result = text.strip()
    for prefix in ["Gemini said", "Gemini said\n", "Gemini said "]:
        if result.startswith(prefix):
            result = result[len(prefix):].strip()
    return result


async def _composer_is_empty(page: Any) -> bool:
    try:
        from subscription_bridge.providers.gemini.prompt_io import find_composer, get_composer_text
        composer = await find_composer(page)
        text = await get_composer_text(page, composer)
        return len(text.strip()) == 0
    except Exception:
        return False


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
