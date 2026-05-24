from __future__ import annotations

from typing import Any

from subscription_bridge import __version__
from subscription_bridge.browser.playwright_manager import PlaywrightManager
from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.providers import FakeProviderAdapter, ProviderRegistry
from subscription_bridge.providers.gemini import GeminiProviderAdapter
from subscription_bridge.tools import (
    BashTool,
    CodebaseSearchTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    GitDiffTool,
    GlobTool,
    GrepTool,
    PatchTool,
    TodoWriteTool,
    ToolRegistry,
)
from subscription_bridge.utils.config import load_config


class AppDependencies:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._registry: ProviderRegistry | None = None
        self._gemini_adapter: GeminiProviderAdapter | None = None
        self._session_pool: SessionPool | None = None
        self._playwright_manager: PlaywrightManager | None = None
        self._browser_started = False

    def load_config(self) -> dict[str, Any]:
        self._config = load_config()
        return self._config

    def get_registry(self) -> ProviderRegistry:
        if self._registry is None:
            self._registry = ProviderRegistry()
            self._registry.register(FakeProviderAdapter())
        return self._registry

    def get_tool_registry(self) -> ToolRegistry:
        r = ToolRegistry()
        r.register(FileReadTool())
        r.register(FileWriteTool())
        r.register(FileEditTool())
        r.register(GrepTool())
        r.register(BashTool())
        r.register(GitDiffTool())
        r.register(PatchTool())
        r.register(GlobTool())
        r.register(CodebaseSearchTool())
        r.register(TodoWriteTool())
        return r

    async def ensure_browser(self) -> None:
        if self._browser_started:
            return
        config = self.load_config()
        browser_config = config.get("browser", {})
        self._playwright_manager = PlaywrightManager(config)
        await self._playwright_manager.start()
        max_sessions = int(browser_config.get("max_sessions", 3))
        ttl = float(browser_config.get("session_ttl_seconds", 600))
        self._session_pool = SessionPool(max_sessions=max_sessions, session_ttl_seconds=ttl)
        self._browser_started = True

    async def get_gemini_adapter(self) -> GeminiProviderAdapter:
        if self._gemini_adapter is not None:
            return self._gemini_adapter

        await self.ensure_browser()

        pool = self._session_pool
        pm = self._playwright_manager

        async def _page_factory() -> Any:
            return await pm.create_page()  # type: ignore[union-attr]

        self._gemini_adapter = GeminiProviderAdapter(
            session_pool=pool,  # type: ignore[arg-type]
            page_factory=_page_factory,
        )
        reg = self.get_registry()
        reg.register(self._gemini_adapter)
        return self._gemini_adapter

    def get_session_pool(self) -> SessionPool | None:
        return self._session_pool

    def get_version(self) -> str:
        return __version__

    async def get_provider_healths(self) -> dict[str, str]:
        result: dict[str, str] = {"fake": "ready"}

        try:
            adapter = await self.get_gemini_adapter()
            ok = await adapter.health_check()
            if ok:
                result["gemini"] = "ready"
            else:
                from subscription_bridge.providers.gemini.health import check_provider_health

                session = await adapter._pool.acquire(
                    "gemini", "api-health", lambda: adapter._page_factory()
                )
                try:
                    health = await check_provider_health(session.page)
                    result["gemini"] = health.get("detail", "login_required")
                finally:
                    await adapter._pool.release(session.session_id)
        except Exception as e:
            err = str(e)
            if "login" in err.lower():
                result["gemini"] = "login_required"
            else:
                result["gemini"] = "unavailable"

        return result
