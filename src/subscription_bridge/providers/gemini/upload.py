from __future__ import annotations

import time
from typing import Any

from subscription_bridge.providers.gemini.attachments import AttachmentInfo, UploadConfig
from subscription_bridge.providers.gemini.selectors import get_selector


class UploadError(Exception):
    ...


async def find_file_input(page: Any) -> Any:
    upload_inputs = get_selector("upload_inputs")
    for selector in upload_inputs:
        try:
            el = page.locator(selector).first
            visible = await el.is_visible()
            if visible:
                return el
        except Exception:
            continue
    return None


async def add_files_via_attach_button(page: Any) -> Any:
    attach_selectors = get_selector("attach_buttons")
    for selector in attach_selectors:
        try:
            el = page.locator(selector).first
            visible = await el.is_visible()
            if visible:
                await el.click()
                await _sleep(1.0)
                return await find_file_input(page)
        except Exception:
            continue
    return None


async def upload_files(
    page: Any,
    attachments: list[AttachmentInfo],
    config: UploadConfig,
) -> dict[str, Any]:
    if not attachments:
        return {"success": True, "uploaded": 0}

    file_input = await find_file_input(page)
    if file_input is None:
        file_input = await add_files_via_attach_button(page)
    if file_input is None:
        inputs = get_selector("upload_inputs")
        for selector in inputs:
            try:
                candidate = page.locator(selector).first
                exists = await candidate.count()
                if exists > 0:
                    file_input = candidate
                    break
            except Exception:
                continue

    if file_input is None:
        raise UploadError("Could not find file input in Gemini UI")

    resolved_paths = [a.resolved_path for a in attachments]

    try:
        await file_input.set_input_files(resolved_paths)
    except Exception as e:
        raise UploadError(f"Gemini file input rejected upload: {e}") from e

    settled = await wait_for_uploads_to_settle(
        page,
        expected_count=len(attachments),
        timeout=config.upload_timeout_seconds,
    )

    return {
        "success": True,
        "uploaded": len(attachments),
        "settled": settled,
        "paths": [a.path for a in attachments],
        "categories": [a.category for a in attachments],
    }


async def wait_for_uploads_to_settle(
    page: Any,
    expected_count: int,
    timeout: float = 180.0,
) -> bool:
    deadline = time.monotonic() + timeout
    last_count = 0
    stable_cycles = 0

    while time.monotonic() < deadline:
        current = await visible_attachment_count(page)
        progress = await upload_activity_present(page)

        if current >= expected_count and not progress:
            stable_cycles += 1
            if stable_cycles >= 3:
                return True
        else:
            stable_cycles = 0

        if current > last_count and not progress:
            stable_cycles += 1
            if stable_cycles >= 3:
                return True

        last_count = current
        await _sleep(0.5)

    return False


async def visible_attachment_count(page: Any) -> int:
    preview_selectors = get_selector("attachment_previews")
    for selector in preview_selectors:
        try:
            elements = await page.query_selector_all(selector)
            visible_count = 0
            for el in elements:
                try:
                    if await el.is_visible():
                        visible_count += 1
                except Exception:
                    continue
            if visible_count > 0:
                return visible_count
        except Exception:
            continue
    return 0


async def upload_activity_present(page: Any) -> bool:
    progress_selectors = get_selector("progress")
    for selector in progress_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    if await el.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
