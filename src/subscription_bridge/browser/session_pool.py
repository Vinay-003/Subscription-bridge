from __future__ import annotations

import asyncio
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
        self._acquire_lock = asyncio.Lock()

    async def acquire(
        self,
        provider_name: str,
        run_id: str,
        page_factory: Any,
        *,
        allow_cross_run_reuse: bool = True,
    ) -> TabSession:
        # Avoid duplicate browser tabs when concurrent first requests use one conversation key.
        async with self._acquire_lock:
            return await self._acquire_impl(
                provider_name, run_id, page_factory,
                allow_cross_run_reuse=allow_cross_run_reuse,
            )

    async def _acquire_impl(
        self,
        provider_name: str,
        run_id: str,
        page_factory: Any,
        *,
        allow_cross_run_reuse: bool = True,
    ) -> TabSession:
        await self._evict_stale()

        existing = self._find_by_run_id(run_id, provider_name)
        if existing is not None:
            ok = await existing.ensure_alive()
            if ok:
                # Serialize requests that target the same browser conversation.
                await existing.operation_lock.acquire()
                existing.mark_busy(run_id)
                return existing
            self._sessions.pop(existing.session_id, None)

        if allow_cross_run_reuse:
            idle = self._find_idle(provider_name)
            if idle is not None:
                ok = await idle.ensure_alive()
                if ok:
                    await idle.operation_lock.acquire()
                    if idle.owner_run_id != run_id:
                        # A different conversation is taking over this tab. Its
                        # provider-side chat history must be reset by the adapter.
                        idle.has_active_conversation = False
                        idle.selected_model_variant = None
                    idle.mark_busy(run_id, replace_owner=True)
                    return idle
                self._sessions.pop(idle.session_id, None)

        active_count = sum(
            1 for s in self._sessions.values()
            if s.state not in (SessionState.CLOSED, SessionState.CRASHED)
        )
        if active_count >= self._max_sessions and not allow_cross_run_reuse:
            # Preserve session isolation without permanently exhausting the pool:
            # retire the least-recently-used idle conversation, never a busy tab.
            idle_candidates = sorted(
                (s for s in self._sessions.values() if s.state == SessionState.IDLE),
                key=lambda session: session.last_used_at,
            )
            while idle_candidates and active_count >= self._max_sessions:
                victim = idle_candidates.pop(0)
                self._sessions.pop(victim.session_id, None)
                await victim.close()
                active_count -= 1
        if active_count >= self._max_sessions:
            msg = (
                f"Max sessions ({self._max_sessions}) reached. "
                f"All browser sessions are busy; wait for one to finish or increase max_sessions."
            )
            raise SessionPoolError(msg)

        page = await self._make_page(page_factory, provider_name)
        session = TabSession(provider_name=provider_name, page=page)
        await session.operation_lock.acquire()
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
        if session.operation_lock.locked():
            session.operation_lock.release()

    async def reset(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        # Reset only after any in-flight prompt on this tab has finished.
        await session.operation_lock.acquire()
        try:
            try:
                url = await session.get_url()
                if url:
                    await session.page.goto("about:blank")
            except Exception:
                pass
            session.mark_idle()
            session.owner_run_id = None
            session.has_active_conversation = False
            session.selected_model_variant = None
        finally:
            session.operation_lock.release()

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
                "owner_run_id": session.owner_run_id,
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

    def _find_by_run_id(self, run_id: str, provider_name: str) -> TabSession | None:
        if not run_id:
            return None
        for session in self._sessions.values():
            if (
                session.provider_name == provider_name
                and (session.current_run_id == run_id or session.owner_run_id == run_id)
                and session.state not in (SessionState.CLOSED, SessionState.CRASHED)
            ):
                return session
        return None

    @staticmethod
    async def _make_page(page_factory: Any, provider_name: str) -> Any:
        """Call either a provider-aware factory or a legacy zero-argument factory."""
        import inspect

        try:
            signature = inspect.signature(page_factory)
            accepts_arg = any(
                p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
                for p in signature.parameters.values()
            )
        except (TypeError, ValueError):
            accepts_arg = False
        if accepts_arg:
            return await page_factory(provider_name)
        return await page_factory()

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
