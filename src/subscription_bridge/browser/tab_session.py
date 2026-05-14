from __future__ import annotations

import time
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from subscription_bridge.utils.paths import get_debug_dir


class SessionState(StrEnum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    CRASHED = "CRASHED"
    CLOSED = "CLOSED"


class TabSession:
    def __init__(
        self,
        provider_name: str,
        page: Any,
    ) -> None:
        self.session_id: str = f"tab-{uuid.uuid4().hex[:12]}"
        self.provider_name: str = provider_name
        self._page: Any = page
        self.created_at: float = time.monotonic()
        self.last_used_at: float = self.created_at
        self.state: SessionState = SessionState.IDLE
        self.current_run_id: str | None = None
        self.has_active_conversation: bool = False

    @property
    def page(self) -> Any:
        return self._page

    def mark_busy(self, run_id: str) -> None:
        self.state = SessionState.BUSY
        self.current_run_id = run_id
        self.last_used_at = time.monotonic()

    def mark_idle(self) -> None:
        self.state = SessionState.IDLE
        self.current_run_id = None
        self.last_used_at = time.monotonic()

    def mark_degraded(self) -> None:
        if self.state != SessionState.CRASHED:
            self.state = SessionState.DEGRADED
            self.last_used_at = time.monotonic()

    def mark_crashed(self) -> None:
        self.state = SessionState.CRASHED
        self.last_used_at = time.monotonic()

    async def close(self) -> None:
        self.state = SessionState.CLOSED
        self.current_run_id = None
        self.last_used_at = time.monotonic()
        try:
            await self._page.close()
        except Exception:
            pass

    async def ensure_alive(self) -> bool:
        if self.state in (SessionState.CLOSED, SessionState.CRASHED):
            return False
        try:
            _ = await self._page.evaluate("1")
            return True
        except Exception:
            self.mark_crashed()
            return False

    async def screenshot_debug(self, label: str) -> Path | None:
        debug_dir = get_debug_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        filename = f"{timestamp}_{self.session_id}_{safe_label}.png"
        out_path = debug_dir / filename
        try:
            await self._page.screenshot(path=str(out_path))
            return out_path
        except Exception:
            return None

    async def get_url(self) -> str:
        try:
            result = await self._page.evaluate("window.location.href")
            return str(result)
        except Exception:
            return ""

    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used_at

    def __repr__(self) -> str:
        return (
            f"TabSession(id={self.session_id}, provider={self.provider_name}, "
            f"state={self.state.value}, run={self.current_run_id})"
        )
