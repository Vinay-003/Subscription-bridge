from __future__ import annotations

import re
import time
from typing import Any

from subscription_bridge.providers.gemini.selectors import get_selector


async def submission_activity_report(page: Any) -> dict[str, Any]:
    script = r"""
    () => {
        const root = document.querySelector('main') || document.body;
        const visible = el => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return (
                r.width > 0 && r.height > 0
                && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'
            );
        };
        const textOf = el => (
            (el.getAttribute('aria-label') || '') + ' '
            + (el.getAttribute('title') || '') + ' '
            + (el.innerText || '')
        ).replace(/\s+/g, ' ').trim().toLowerCase();
        const bodyText = (root.innerText || '').replace(/\s+/g, ' ').toLowerCase();
        const buttons = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
        const buttonText = buttons.map(textOf).join(' | ');
        const stopVisible = /stop response|cancel generation|stop generating|stop streaming/.test(buttonText);
        const thinkingVisible = /show thinking|creating image|generating/.test(buttonText);
        let progressVisible = false;
        const progressSel = '[role="progressbar"],mat-progress-spinner,mat-progress-bar,.spinner,.loading,.progress';
        for (const el of document.querySelectorAll(progressSel)) {
            if (visible(el)) { progressVisible = true; break; }
        }
        const selectors = [
            'model-response','.model-response','.response-container',
            '[data-response-index]','[data-chunk-index]','[data-testid*="response"]'
        ];
        const responseEls = new Set();
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) if (visible(el)) responseEls.add(el);
        }
        const responses = Array.from(responseEls).sort((a,b) => {
            const pos = a.compareDocumentPosition(b);
            return pos & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
        });
        const last = responses[responses.length-1];
        const lastText = last ? (last.innerText || last.textContent || '').trim() : '';
        const path = window.location.pathname || '';
        const conversationUrl = /^\/(?:u\/\d+\/)?app(?:\/|$)/.test(path);
        return {
            stopVisible,
            thinkingVisible,
            progressVisible,
            assistantCount: responses.length,
            lastResponseLength: lastText.length,
            lastResponseText: lastText,
            conversationUrl,
            path
        };
    }
    """
    try:
        return dict(await page.evaluate(script) or {})
    except Exception:
        return {}


async def generation_in_progress(page: Any) -> bool:
    report = await submission_activity_report(page)
    return bool(
        report.get("stopVisible") or report.get("thinkingVisible") or report.get("progressVisible")
    )


async def wait_for_send_confirmation(page: Any, timeout: float = 35.0, pre_send_count: int = 0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        report = await submission_activity_report(page)
        if report.get("stopVisible") or report.get("progressVisible"):
            return True
        if int(report.get("assistantCount", 0)) > pre_send_count:
            return True
        # Do not accept an old conversation URL or an already-empty composer as
        # proof that this request was submitted; both are true before the send.
        await _sleep(0.5)
    return False


async def wait_for_response_complete(
    page: Any, timeout: float = 120.0, poll_interval: float = 0.5, pre_send_count: int = 0
) -> bool:
    deadline = time.monotonic() + timeout
    last_text = ""
    stable_cycles = 0
    observed_new_response = False
    while time.monotonic() < deadline:
        report = await submission_activity_report(page)
        count = int(report.get("assistantCount", 0))
        text = str(report.get("lastResponseText", "")).strip()
        generating = bool(report.get("stopVisible") or report.get("progressVisible"))
        if count > pre_send_count and text:
            observed_new_response = True
        if observed_new_response and not generating and text:
            if text == last_text:
                stable_cycles += 1
                if stable_cycles >= 4:
                    return True
            else:
                stable_cycles = 0
            last_text = text
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
    result = re.sub(r"(?im)^\s*copy code\s*\n", "", result)
    result = re.sub(r"(?im)^\s*(?:show thinking|hide thinking)\s*$", "", result)
    if result.lower().startswith("you stopped this response"):
        return ""
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
