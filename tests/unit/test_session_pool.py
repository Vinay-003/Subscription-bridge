from __future__ import annotations

import pytest

from subscription_bridge.browser.session_pool import SessionPool, SessionPoolError
from subscription_bridge.browser.tab_session import SessionState


class FakePage:
    def __init__(self) -> None:
        self._closed = False

    async def evaluate(self, expr: str) -> int:
        if self._closed:
            raise RuntimeError("page closed")
        return 1

    async def goto(self, url: str) -> None:
        pass

    async def close(self) -> None:
        self._closed = True

    async def screenshot(self, path: str) -> bytes:
        return b"fake"


async def _page_factory() -> FakePage:
    return FakePage()


@pytest.fixture
def pool() -> SessionPool:
    return SessionPool(max_sessions=3, session_ttl_seconds=600.0)


@pytest.mark.asyncio
async def test_acquire_creates_session(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    assert session is not None
    assert session.state == SessionState.BUSY
    assert session.current_run_id == "run-001"
    assert pool.active_count == 1
    assert pool.total_count == 1


@pytest.mark.asyncio
async def test_acquire_reuse_idle(pool: SessionPool) -> None:
    s1 = await pool.acquire("test", "run-001", _page_factory)
    await pool.release(s1.session_id)
    assert pool.active_count == 0
    assert pool.idle_count == 1

    s2 = await pool.acquire("test", "run-002", _page_factory)
    assert s2.session_id == s1.session_id
    assert s2.state == SessionState.BUSY
    assert s2.current_run_id == "run-002"


@pytest.mark.asyncio
async def test_acquire_max_sessions(pool: SessionPool) -> None:
    await pool.acquire("test", "run-001", _page_factory)
    await pool.acquire("test", "run-002", _page_factory)
    await pool.acquire("test", "run-003", _page_factory)

    with pytest.raises(SessionPoolError, match="Max sessions"):
        await pool.acquire("test", "run-004", _page_factory)


@pytest.mark.asyncio
async def test_release_makes_idle(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    assert pool.active_count == 1

    await pool.release(session.session_id)
    assert pool.active_count == 0
    assert pool.idle_count == 1


@pytest.mark.asyncio
async def test_release_nonexistent(pool: SessionPool) -> None:
    await pool.release("nonexistent")


@pytest.mark.asyncio
async def test_reset_session(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    await pool.reset(session.session_id)
    assert session.state == SessionState.IDLE


@pytest.mark.asyncio
async def test_close_session(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    await pool.close(session.session_id)
    assert pool.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_close_all(pool: SessionPool) -> None:
    await pool.acquire("test", "run-001", _page_factory)
    await pool.acquire("test", "run-002", _page_factory)
    assert pool.total_count == 2

    await pool.close_all()
    assert pool.total_count == 0


@pytest.mark.asyncio
async def test_health_check(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    ok = await pool.health_check(session.session_id)
    assert ok is True

    ok = await pool.health_check("nonexistent")
    assert ok is False


@pytest.mark.asyncio
async def test_list_sessions(pool: SessionPool) -> None:
    await pool.acquire("test", "run-001", _page_factory)
    sessions = pool.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["provider_name"] == "test"
    assert sessions[0]["state"] == "BUSY"


@pytest.mark.asyncio
async def test_get_session(pool: SessionPool) -> None:
    session = await pool.acquire("test", "run-001", _page_factory)
    assert pool.get_session(session.session_id) is session
    assert pool.get_session("nonexistent") is None


def test_initial_counts(pool: SessionPool) -> None:
    assert pool.active_count == 0
    assert pool.idle_count == 0
    assert pool.total_count == 0
