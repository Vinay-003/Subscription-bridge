from __future__ import annotations

import re
import time
from typing import Any

from subscription_bridge.providers.gemini.selectors import get_selector, get_timeout


def normalize_prompt_compare(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def compact_prompt_compare(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_prompt_compare(text)).strip()


def sample_chunks(text: str, chunk_size: int = 96) -> list[str]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    positions = [
        0,
        int(len(text) * 0.25),
        int(len(text) * 0.50),
        int(len(text) * 0.75),
        max(0, len(text) - chunk_size),
    ]
    chunks: list[str] = []
    seen: set[str] = set()
    for pos in positions:
        pos = min(max(0, pos), max(0, len(text) - chunk_size))
        chunk = text[pos : pos + chunk_size].strip()
        if len(chunk) < 24:
            continue
        if chunk not in seen:
            seen.add(chunk)
            chunks.append(chunk)
    return chunks


def prompt_integrity_report(expected: str, actual: str, min_ratio: float = 0.98) -> dict[str, Any]:
    expected_compact = compact_prompt_compare(expected)
    actual_compact = compact_prompt_compare(actual)
    expected_len = len(expected_compact)
    actual_len = len(actual_compact)
    ratio = (actual_len / expected_len) if expected_len else 1.0

    prefix_len = min(160, expected_len)
    suffix_len = min(160, expected_len)
    prefix_ok = bool(expected_len == 0 or actual_compact.startswith(expected_compact[:prefix_len]))
    suffix_ok = bool(expected_len == 0 or actual_compact.endswith(expected_compact[-suffix_len:]))

    chunks = sample_chunks(expected_compact)
    found_chunks = sum(1 for chunk in chunks if chunk in actual_compact)
    chunks_ok = found_chunks == len(chunks)
    ok = bool(ratio >= min_ratio and prefix_ok and suffix_ok and chunks_ok)

    return {
        "ok": ok,
        "expected_len": expected_len,
        "actual_len": actual_len,
        "ratio": round(ratio, 4),
        "prefix_ok": prefix_ok,
        "suffix_ok": suffix_ok,
        "chunks_found": found_chunks,
        "chunks_total": len(chunks),
        "actual_preview_start": actual_compact[:180],
        "actual_preview_end": actual_compact[-180:] if actual_compact else "",
    }


def format_integrity(report: dict[str, Any]) -> str:
    return (
        f"expected={report.get('expected_len')} compact chars, "
        f"actual={report.get('actual_len')} compact chars, "
        f"ratio={report.get('ratio', 0.0):.1%}, "
        f"prefix={report.get('prefix_ok')}, suffix={report.get('suffix_ok')}, "
        f"chunks={report.get('chunks_found')}/{report.get('chunks_total')}"
    )


async def find_composer(page: Any) -> Any:
    composers = get_selector("composer")
    timeout = get_timeout("composer", 30000) / 1000
    last_error: Exception | None = None
    for selector in composers:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout * 1000)
            return loc
        except Exception as exc:
            last_error = exc
    msg = f"Could not find Gemini composer. Last error: {last_error}"
    raise RuntimeError(msg)


async def get_composer_text(page: Any, composer: Any) -> str:
    script = """
    (root) => {
        function readText(el) {
            if (!el) return '';
            const tag = (el.tagName || '').toLowerCase();
            if (tag === 'textarea' || tag === 'input') return el.value || '';
            if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                return el.innerText || el.textContent || '';
            }
            if (el.querySelector) {
                const child = el.querySelector('textarea, input, [contenteditable="true"], [role="textbox"]');
                if (child) return readText(child);
            }
            return el.innerText || el.textContent || '';
        }
        return readText(root);
    }
    """
    try:
        result = await composer.evaluate(script)
        return str(result or "")
    except Exception:
        return ""


async def focus_composer(page: Any, composer: Any) -> None:
    try:
        await composer.scroll_into_view_if_needed()
    except Exception:
        pass
    for _ in range(3):
        try:
            await composer.click()
            break
        except Exception:
            await page.keyboard.press("Escape")
            await _sleep(0.3)
    await _sleep(0.15)


async def clear_composer(page: Any, composer: Any) -> None:
    await focus_composer(page, composer)
    try:
        await composer.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    await _sleep(0.25)


async def paste_via_keyboard(page: Any, text: str) -> bool:
    try:
        composer = await find_composer(page)
        await clear_composer(page, composer)
        composer = await find_composer(page)
        await focus_composer(page, composer)
        await composer.click()
        await page.keyboard.insert_text(text)
        return True
    except Exception:
        return False


async def paste_via_clipboard(page: Any, text: str) -> bool:
    try:
        probe = await page.evaluate(
            """async (text) => {
                if (!navigator.clipboard || !navigator.clipboard.writeText || !navigator.clipboard.readText) {
                    throw new Error('clipboard unavailable');
                }
                await navigator.clipboard.writeText(text);
                const current = await navigator.clipboard.readText();
                return current === text;
            }""",
            text,
        )
        if not probe:
            return False
        composer = await find_composer(page)
        await clear_composer(page, composer)
        composer = await find_composer(page)
        await focus_composer(page, composer)
        await page.keyboard.press("Control+v")
        return True
    except Exception:
        return False


async def paste_via_js(page: Any, text: str) -> bool:
    script = """
    (el, text) => {
        el.scrollIntoView({block:'center', inline:'center'});
        el.focus();
        const tag = (el.tagName || '').toLowerCase();
        if (tag === 'textarea' || tag === 'input') {
            el.value = '';
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.value = text;
            el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertFromPaste', data:text}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            return true;
        }
        const dt = new DataTransfer();
        dt.setData('text/plain', text);
        const pasteEvent = new ClipboardEvent('paste', {bubbles:true, cancelable:true, clipboardData:dt});
        el.dispatchEvent(pasteEvent);
        if ((el.innerText || '').trim().length < 10) {
            el.textContent = '';
            document.execCommand('insertText', false, text);
        }
        el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertFromPaste', data:text}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        return true;
    }
    """
    try:
        composer = await find_composer(page)
        await clear_composer(page, composer)
        composer = await find_composer(page)
        await focus_composer(page, composer)
        return bool(await composer.evaluate(script, text))
    except Exception:
        return False


async def wait_for_prompt_integrity(
    page: Any,
    expected: str,
    timeout: float,
    min_ratio: float,
) -> tuple[Any, str, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_composer: Any = None
    last_actual = ""
    last_report = prompt_integrity_report(expected, "", min_ratio)
    while time.monotonic() < deadline:
        try:
            last_composer = await find_composer(page)
            last_actual = await get_composer_text(page, last_composer)
            last_report = prompt_integrity_report(expected, last_actual, min_ratio)
            if last_report["ok"]:
                return last_composer, last_actual, last_report
        except Exception:
            pass
        await _sleep(0.5)
    if last_composer is None:
        last_composer = await find_composer(page)
    return last_composer, last_actual, last_report


def _prompt_methods() -> list[str]:
    return ["keyboard", "js"]


async def set_prompt_text(
    page: Any,
    text: str,
    verify_timeout: float = 35.0,
    min_integrity_ratio: float = 0.98,
) -> Any:
    last_report = prompt_integrity_report(text, "", min_integrity_ratio)

    for method in _prompt_methods():
        if method == "keyboard":
            inserted = await paste_via_keyboard(page, text)
        elif method == "js":
            inserted = await paste_via_js(page, text)
        else:
            inserted = False

        if not inserted:
            continue

        composer, actual, report = await wait_for_prompt_integrity(
            page, expected=text, timeout=verify_timeout, min_ratio=min_integrity_ratio,
        )
        last_report = report
        if report["ok"]:
            return composer

    raise RuntimeError(
        "Prompt was not inserted completely; refusing to send partial prompt. "
        + format_integrity(last_report)
    )


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
