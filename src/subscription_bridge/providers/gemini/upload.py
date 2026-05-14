from __future__ import annotations

import time
from typing import Any

from subscription_bridge.providers.gemini.attachments import AttachmentInfo, UploadConfig


class UploadError(Exception):
    ...


async def upload_files(
    page: Any,
    attachments: list[AttachmentInfo],
    config: UploadConfig,
) -> dict[str, Any]:
    if not attachments:
        return {"success": True, "uploaded": 0, "method": "none"}

    resolved_paths = [a.resolved_path for a in attachments]

    uploaded = await _upload_via_cdp(page, resolved_paths)
    if not uploaded:
        uploaded = await _upload_via_playwright(page, resolved_paths)
    if not uploaded:
        await _open_attach_menu(page)
        await _sleep(0.5)
        uploaded = await _upload_via_cdp(page, resolved_paths)
    if not uploaded:
        uploaded = await _upload_via_playwright(page, resolved_paths)

    if uploaded:
        settled = await _wait_for_uploads_settle(page, len(attachments), config.upload_timeout_seconds)
        return {
            "success": True,
            "uploaded": len(attachments),
            "settled": settled,
            "method": "browser_upload",
            "paths": [a.path for a in attachments],
            "categories": [a.category for a in attachments],
        }

    text_contents = []
    for a in attachments:
        try:
            with open(a.resolved_path, encoding="utf-8") as f:
                content = f.read(config.max_file_bytes)
            text_contents.append({
                "filename": a.filename,
                "content": content,
                "category": a.category,
            })
        except (OSError, UnicodeDecodeError):
            raise UploadError(
                f"Could not upload {a.filename}: browser upload failed "
                "and file is not a readable text file"
            )

    return {
        "success": True,
        "uploaded": len(attachments),
        "settled": True,
        "method": "text_inline",
        "paths": [a.path for a in attachments],
        "categories": [a.category for a in attachments],
        "text_contents": text_contents,
        "inline_hint": True,
    }


async def _upload_via_cdp(page: Any, file_paths: list[str]) -> bool:
    try:
        cdp = await page.context.new_cdp_session(page)
    except Exception:
        return False

    for attempt in range(1, 4):
        try:
            doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
            root_id = doc["root"]["nodeId"]
            result = await cdp.send(
                "DOM.querySelectorAll", {"nodeId": root_id, "selector": "input[type='file']"}
            )
            node_ids = result.get("nodeIds", [])
        except Exception:
            node_ids = []

        if not node_ids:
            if attempt < 3:
                await _open_attach_menu(page)
                await _sleep(0.6)
                continue
            return False

        for node_id in reversed(node_ids):
            try:
                attrs_result = await cdp.send("DOM.describeNode", {"nodeId": int(node_id)})
                attrs = attrs_result.get("node", {}).get("attributes", []) or []
                attr_dict = dict(zip(attrs[0::2], attrs[1::2]))
                if "disabled" in attr_dict:
                    continue
            except Exception:
                continue
            try:
                await cdp.send(
                    "DOM.setFileInputFiles", {"nodeId": int(node_id), "files": file_paths}
                )
                await _dispatch_input_events(cdp, int(node_id))
                return True
            except Exception:
                continue
        return False
    return False


async def _dispatch_input_events(cdp: Any, node_id: int) -> None:
    try:
        resolved = await cdp.send("DOM.resolveNode", {"nodeId": node_id})
        object_id = resolved.get("object", {}).get("objectId")
        if not object_id:
            return
        await cdp.send(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": """
                    function() {
                        try { this.dispatchEvent(new Event('input', {bubbles: true})); } catch (e) {}
                        try { this.dispatchEvent(new Event('change', {bubbles: true})); } catch (e) {}
                        return true;
                    }
                """,
            },
        )
    except Exception:
        pass


async def _upload_via_playwright(page: Any, file_paths: list[str]) -> bool:
    selectors = ["input[type='file'][multiple]", "input[type='file']"]
    for selector in selectors:
        try:
            loc = page.locator(selector).last
            await loc.wait_for(state="attached", timeout=1500)
            await loc.set_input_files(file_paths, timeout=0)
            return True
        except Exception:
            continue
    return False


async def _open_attach_menu(page: Any) -> None:
    script = """
    () => {
        const main = document.querySelector('main') || document.body;
        function visible(el) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }
        const composer = document.querySelector(
            'rich-textarea div[contenteditable="true"], ' +
            'div[contenteditable="true"][role="textbox"], ' +
            'main div[contenteditable="true"]'
        );
        if (!composer) return false;
        const cr = composer.getBoundingClientRect();
        const nodes = Array.from(main.querySelectorAll('button,[role="button"]'));
        const candidates = [];
        for (const el of nodes) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            if (r.width <= 0 || r.height <= 0 || s.display === 'none' || s.visibility === 'hidden') continue;
            const t = ((el.getAttribute('aria-label') || '') + ' ' +
                       (el.getAttribute('title') || '') + ' ' +
                       (el.innerText || '')).replace(/\\s+/g, ' ').trim().toLowerCase();
            if (t.includes('upload files') || t.includes('add from drive') ||
                t.includes('photos') || t.includes('import code') || t.includes('notebooklm')) continue;
            const looksLikePlus = t === '+' || t.includes('add files') ||
                t.includes('attach file') || t.includes('attach files');
            if (!looksLikePlus) continue;
            const centerY = r.top + r.height / 2;
            const compCenterY = cr.top + cr.height / 2;
            const nearComposer = Math.abs(centerY - compCenterY) < 220;
            if (!nearComposer) continue;
            candidates.push({el, dist: Math.abs(centerY - compCenterY), left: r.left});
        }
        if (!candidates.length) return false;
        candidates.sort((a, b) => (a.dist - b.dist) || (a.left - b.left));
        candidates[0].el.scrollIntoView({block: 'center', inline: 'center'});
        candidates[0].el.click();
        return true;
    }
    """
    try:
        await page.evaluate(script)
    except Exception:
        pass


async def _visible_uploaded_image_count(page: Any) -> int:
    script = """
    () => {
        const main = document.querySelector('main') || document.body;
        function visible(el) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width >= 32 && r.height >= 32 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }
        function forbidden(el) {
            return !!el.closest('nav,[role="navigation"],header,model-response,.model-response,[data-author="model"]');
        }
        function srcBad(src) {
            const s = (src || '').toLowerCase();
            if (!s) return true;
            if (s.includes('googlelogo') || s.includes('gstatic.com')) return true;
            if (s.includes('/a-/') || s.includes('avatar') || s.includes('profile')) return true;
            return false;
        }
        let count = 0;
        const seen = new Set();
        for (const img of Array.from(main.querySelectorAll('img'))) {
            const src = img.currentSrc || img.src || '';
            if (seen.has(src)) continue;
            seen.add(src);
            if (srcBad(src) || forbidden(img) || !visible(img)) continue;
            count += 1;
        }
        return count;
    }
    """
    try:
        return int(await page.evaluate(script) or 0)
    except Exception:
        return 0


async def _upload_activity_present(page: Any) -> bool:
    script = """
    () => {
        const main = document.querySelector('main') || document.body;
        const txt = (main.innerText || '').toLowerCase();
        if (txt.includes('uploading') || txt.includes('attaching') || txt.includes('scanning')) return true;
        for (const el of Array.from(main.querySelectorAll(
            '[role="progressbar"], mat-progress-bar, mat-progress-spinner, ' +
            '[class*="spinner" i], [class*="loading" i], [class*="progress" i]'
        ))) {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            if (r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden') return true;
        }
        return false;
    }
    """
    try:
        return bool(await page.evaluate(script))
    except Exception:
        return False


async def _wait_for_uploads_settle(
    page: Any,
    expected_count: int,
    timeout: float = 180.0,
) -> bool:
    deadline = time.monotonic() + timeout
    stable_since: float | None = None
    last_state: tuple[int, bool] | None = None

    while time.monotonic() < deadline:
        count = await _visible_uploaded_image_count(page)
        active = await _upload_activity_present(page)
        state = (count, active)

        if state != last_state:
            stable_since = time.monotonic()
            last_state = state

        if count >= expected_count and not active:
            if stable_since and (time.monotonic() - stable_since) >= 2.0:
                return True
        await _sleep(0.5)
    return False


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
