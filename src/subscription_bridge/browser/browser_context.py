from __future__ import annotations

from typing import Any


class ContextManagerError(Exception):
    ...


class BrowserContextManager:
    def __init__(self, playwright_manager: Any) -> None:
        self._pm = playwright_manager

    async def grant_permissions(
        self,
        permissions: list[str] | None = None,
        origin: str = "",
    ) -> None:
        context = self._pm.context
        if context is None:
            return

        perms = permissions or ["clipboard-read", "clipboard-write"]
        try:
            await context.grant_permissions(perms, origin=origin)
        except Exception:
            pass

    async def create_page(self) -> Any:
        page = await self._pm.create_page()
        return page

    async def navigate(self, page: Any, url: str, timeout_ms: int = 60000) -> None:
        try:
            from playwright.async_api import TimeoutError as PWTimeoutError

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except PWTimeoutError:
            current = ""
            try:
                current = await page.evaluate("window.location.href")
            except Exception:
                pass
            if current and current != "about:blank":
                return
            raise

    async def close_context(self) -> None:
        await self._pm.stop()

    async def take_screenshot(self, page: Any, path: str) -> bool:
        try:
            await page.screenshot(path=path)
            return True
        except Exception:
            return False

    async def execute_js(self, page: Any, script: str) -> Any:
        try:
            return await page.evaluate(script)
        except Exception:
            return None

    @property
    def is_ready(self) -> bool:
        return self._pm.is_launched and self._pm.context is not None
