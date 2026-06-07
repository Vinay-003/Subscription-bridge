from __future__ import annotations

import time
from typing import Any

from subscription_bridge.browser.tab_session import SessionState, TabSession


class SessionPoolError(Exception):
    ...


class SessionPool:
    def __init__(
        self,
        max_sessions: int = 3,
        session_ttl_seconds: float = 600.0,
    ) -> None:
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl_seconds
        self._sessions: dict[str, TabSession] = {}

    async def acquire(self, provider_name: str, run_id: str, page_factory: Any) -> TabSession:
        await self._evict_stale()

        existing = self._find_by_run_id(run_id)
        if existing is not None:
            ok = await existing.ensure_alive()
            if ok:
                existing.mark_busy(run_id)
                return existing
            self._sessions.pop(existing.session_id, None)

        idle = self._find_idle(provider_name)
        if idle is not None:
            ok = await idle.ensure_alive()
            if ok:
                idle.mark_busy(run_id)
                return idle
            self._sessions.pop(idle.session_id, None)

        active_count = sum(
            1 for s in self._sessions.values()
            if s.state not in (SessionState.CLOSED, SessionState.CRASHED)
        )
        if active_count >= self._max_sessions:
            msg = (
                f"Max sessions ({self._max_sessions}) reached. "
                f"Release a session first or increase max_sessions."
            )
            raise SessionPoolError(msg)

        page = await page_factory()
        session = TabSession(provider_name=provider_name, page=page)
        session.mark_busy(run_id)
        self._sessions[session.session_id] = session
        return session

    async def release(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        ok = await session.ensure_alive()
        if ok:
            session.mark_idle()
        else:
            session.mark_crashed()

    async def reset(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            url = await session.get_url()
            if url:
                await session.page.goto("about:blank")
        except Exception:
            pass
        session.mark_idle()

    async def close(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.close()

    async def close_all(self) -> None:
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()

    async def health_check(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        return await session.ensure_alive()

    def list_sessions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for session in self._sessions.values():
            result.append({
                "session_id": session.session_id,
                "provider_name": session.provider_name,
                "state": session.state.value,
                "current_run_id": session.current_run_id,
                "created_at": session.created_at,
                "last_used_at": session.last_used_at,
                "age_seconds": session.age_seconds(),
                "idle_seconds": session.idle_seconds(),
            })
        return result

    def get_session(self, session_id: str) -> TabSession | None:
        return self._sessions.get(session_id)

    @property
    def active_count(self) -> int:
        return sum(
            1 for s in self._sessions.values()
            if s.state == SessionState.BUSY
        )

    @property
    def idle_count(self) -> int:
        return sum(
            1 for s in self._sessions.values()
            if s.state == SessionState.IDLE
        )

    @property
    def total_count(self) -> int:
        return len(self._sessions)

    def _find_by_run_id(self, run_id: str) -> TabSession | None:
        for s in self._sessions.values():
            if s.current_run_id == run_id and s.state not in (
                SessionState.CLOSED, SessionState.CRASHED,
            ):
                return s
        return None

    def _find_idle(self, provider_name: str) -> TabSession | None:
        for session in self._sessions.values():
            if session.state == SessionState.IDLE and session.provider_name == provider_name:
                return session
        return None

    async def _evict_stale(self) -> None:
        now = time.monotonic()
        stale_ids = [
            sid
            for sid, s in self._sessions.items()
            if s.state == SessionState.CRASHED
            or s.state == SessionState.CLOSED
            or (s.state == SessionState.IDLE and now - s.last_used_at > self._session_ttl)
        ]
        for sid in stale_ids:
            session = self._sessions.pop(sid, None)
            if session is not None:
                await session.close()
