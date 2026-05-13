from __future__ import annotations

import time
from typing import Any

_UNSAFE_WORDS_DEFAULT: list[str] = [
    "share conversation",
    "share",
    "rename",
    "delete",
    "remove",
    "archive",
    "more options",
    "recent",
    "activity",
    "settings",
    "help",
    "temporary chat",
    "new chat",
    "upgrade",
    "logout",
]


def default_unsafe_words() -> list[str]:
    return list(_UNSAFE_WORDS_DEFAULT)


def make_bad_words_check(bad_words: list[str]) -> str:
    words_json = str(bad_words)
    return f"""
    (function() {{
        const badWords = {words_json};
        return function(el) {{
            const txt = ((el.getAttribute('aria-label') || '') + ' ' +
                         (el.getAttribute('title') || '') + ' ' +
                         (el.innerText || '')).toLowerCase();
            return badWords.some(function(w) {{ return txt.includes(w); }});
        }};
    }})()
    """


def is_visible_js() -> str:
    return """
    (function(el) {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 &&
               s.display !== 'none' &&
               s.visibility !== 'hidden' &&
               s.opacity !== '0';
    })(el)
    """


def forbidden_area_js() -> str:
    return """
    (function(el) {
        if (!el) return false;
        return !!el.closest('nav, [role="navigation"], ' +
            '[aria-label*="Recent"], [aria-label*="Conversation history"], ' +
            '.conversation-list, .history');
    })(el)
    """


async def safe_click_labels(
    page: Any,
    labels: list[str],
    unsafe_words: list[str] | None = None,
    exact: bool = False,
    timeout: float = 8.0,
) -> bool:
    bad = unsafe_words or _UNSAFE_WORDS_DEFAULT
    labels_json = str(labels)
    bad_json = str(bad)
    exact_str = str(exact).lower()

    script = f"""
    (function() {{
        const labels = {labels_json};
        const exact = {exact_str};
        const badWords = {bad_json};

        function visible(el) {{
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }}

        function inForbiddenArea(el) {{
            return !!el.closest('nav, [role="navigation"], ' +
                '[aria-label*="Recent"], [aria-label*="Conversation history"], ' +
                '.conversation-list, .history');
        }}

        function bad(el) {{
            const txt = ((el.getAttribute('aria-label') || '') + ' ' +
                         (el.getAttribute('title') || '') + ' ' +
                         (el.innerText || '')).toLowerCase();
            return badWords.some(function(w) {{ return txt.includes(w); }});
        }}

        const roots = Array.from(
            document.querySelectorAll('main, header, [role="dialog"], ' +
                '.cdk-overlay-container, body')
        );
        const nodes = [];
        for (const root of roots) {{
            for (const el of root.querySelectorAll(
                'button,a,[role="button"],[role="menuitem"],' +
                '[role="option"],[role="menuitemradio"],mat-option'
            )) {{
                if (!nodes.includes(el)) nodes.push(el);
            }}
        }}

        const candidates = [];
        for (const el of nodes) {{
            if (!visible(el) || bad(el)) continue;
            if (inForbiddenArea(el)) continue;
            const txt = ((el.getAttribute('aria-label') || '') + ' ' +
                         (el.getAttribute('title') || '') + ' ' +
                         (el.innerText || '')).trim().toLowerCase();
            if (!txt) continue;
            for (const label of labels) {{
                if ((exact && txt === label) || (!exact && txt.includes(label))) {{
                    candidates.push(el);
                    break;
                }}
            }}
        }}

        if (!candidates.length) return false;
        candidates.sort(function(a, b) {{
            const ar = a.getBoundingClientRect();
            const br = b.getBoundingClientRect();
            return (br.top - ar.top) || (br.left - ar.left);
        }});
        candidates[0].scrollIntoView({{block:'center', inline:'center'}});
        candidates[0].click();
        return true;
    }})()
    """

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            clicked = await page.evaluate(script)
            if clicked:
                return True
        except Exception:
            pass
        await _sleep(0.3)
    return False


async def dismiss_overlays(page: Any) -> None:
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    overlay_selectors = [
        ".mat-drawer-backdrop",
        ".cdk-overlay-backdrop",
        "[role='dialog'] [aria-label='Close']",
        "button[aria-label*='Close']",
    ]

    for selector in overlay_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    if await el.is_visible():
                        await el.click()
                except Exception:
                    pass
        except Exception:
            pass


async def collect_button_diagnostics(page: Any, near_rect: dict[str, float] | None = None) -> list[str]:
    cr_json = str(near_rect) if near_rect else "null"

    script = f"""
    (function() {{
        const cr = {cr_json};
        function visible(el) {{
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }}
        const out = [];
        const nodes = Array.from(
            document.querySelectorAll('main button, main [role="button"]')
        );
        for (const b of nodes) {{
            if (!visible(b)) continue;
            const r = b.getBoundingClientRect();
            if (cr) {{
                const nearY = r.top < cr.bottom + 220 && r.bottom > cr.top - 120;
                if (!nearY) continue;
            }} else if (r.top < window.innerHeight * 0.45) {{
                continue;
            }}
            const txt = (
                (b.getAttribute('aria-label') || '') + ' | ' +
                (b.getAttribute('title') || '') + ' | ' +
                (b.innerText || '')
            ).replace(/\\s+/g, ' ').trim();
            out.push(
                Math.round(r.left) + ',' + Math.round(r.top) + ' ' +
                Math.round(r.width) + 'x' + Math.round(r.height) + ' ' +
                'disabled=' + (!!b.disabled || b.getAttribute('aria-disabled') === 'true') +
                ' :: ' + txt.slice(0, 140)
            );
            if (out.length >= 12) break;
        }}
        return out;
    }})()
    """

    try:
        result = await page.evaluate(script)
        return list(result or [])
    except Exception:
        return []


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
