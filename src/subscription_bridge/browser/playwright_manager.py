from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

BROWSER_MODES = {"managed", "cdp"}


class PlaywrightLaunchError(Exception):
    ...


class PlaywrightManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    @property
    def is_launched(self) -> bool:
        return self._browser is not None

    @property
    def context(self) -> Any | None:
        return self._context

    @property
    def browser(self) -> Any | None:
        return self._browser

    async def start(self) -> Any:
        browser_config = self._config.get("browser", {})
        mode = str(browser_config.get("mode", "managed")).lower()

        if mode not in BROWSER_MODES:
            msg = f"Invalid browser mode {mode!r}. Must be one of: {', '.join(sorted(BROWSER_MODES))}"
            raise PlaywrightLaunchError(msg)

        if mode == "cdp":
            return await self._start_cdp(browser_config)
        return await self._start_managed(browser_config)

    async def _start_cdp(self, browser_config: dict[str, Any]) -> Any:
        cdp_url = str(browser_config.get("cdp_url", "http://127.0.0.1:9333"))

        self._verify_cdp_reachable(cdp_url)

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            msg = f"Failed to connect to Chrome via CDP at {cdp_url}: {e}"
            raise PlaywrightLaunchError(msg) from e

        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        self._context.set_default_timeout(30000)

        return self._context

    async def _start_managed(self, browser_config: dict[str, Any]) -> Any:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        headless = bool(browser_config.get("headless", False))
        raw_user_dir = str(browser_config.get("user_data_dir", "~/.subscription-bridge/chrome-profile"))
        user_data_dir = str(Path(raw_user_dir).expanduser().resolve())
        raw_dl_dir = str(browser_config.get("downloads_dir", "~/.subscription-bridge/downloads"))
        downloads_dir = str(Path(raw_dl_dir).expanduser().resolve())
        chrome_path = str(browser_config.get("chrome_path", ""))

        Path(downloads_dir).mkdir(parents=True, exist_ok=True)

        launch_args = [
            "--disable-notifications",
            "--disable-popup-blocking",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--start-maximized",
        ]

        launch_opts: dict[str, Any] = {
            "headless": headless,
            "args": launch_args,
            "downloads_path": downloads_dir,
            "accept_downloads": True,
            "bypass_csp": True,
        }

        if chrome_path and Path(chrome_path).exists():
            launch_opts["executable_path"] = chrome_path

        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir,
                **launch_opts,
            )
        except Exception as e:
            msg = f"Failed to launch managed browser (profile: {user_data_dir}): {e}"
            raise PlaywrightLaunchError(msg) from e

        self._context.set_default_timeout(30000)

        if not self._context.pages:
            await self._context.new_page()

        return self._context

    async def create_page(self) -> Any:
        if self._context is None:
            msg = "Browser not started. Call start() first."
            raise PlaywrightLaunchError(msg)
        page = await self._context.new_page()
        return page

    async def stop(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @staticmethod
    def _verify_cdp_reachable(cdp_url: str) -> None:
        from urllib.parse import urlparse

        parsed = urlparse(cdp_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9333

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            sock.close()
        except (TimeoutError, ConnectionRefusedError, OSError) as e:
            msg = (
                f"Cannot reach CDP endpoint at {cdp_url} ({host}:{port}). "
                f"Make sure Chrome is running with --remote-debugging-port={port} "
                f"and a dedicated profile. See docs/README for launch commands."
            )
            raise PlaywrightLaunchError(msg) from e
