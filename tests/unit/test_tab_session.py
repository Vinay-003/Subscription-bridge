from __future__ import annotations

import pytest

from subscription_bridge.browser.tab_session import SessionState, TabSession


class FakePage:
    def __init__(self) -> None:
        self._closed = False
        self._url = "about:blank"

    async def evaluate(self, expr: str) -> int | str:
        if self._closed:
            raise RuntimeError("page closed")
        if "window.location.href" in expr:
            return self._url
        return 1

    async def goto(self, url: str) -> None:
        self._url = url

    async def close(self) -> None:
        self._closed = True

    async def screenshot(self, path: str) -> bytes:
        return b"fake"


@pytest.fixture
def tab_session() -> TabSession:
    page = FakePage()
    return TabSession(provider_name="test", page=page)


def test_tab_session_creation(tab_session: TabSession) -> None:
    assert tab_session.session_id.startswith("tab-")
    assert tab_session.provider_name == "test"
    assert tab_session.state == SessionState.IDLE
    assert tab_session.current_run_id is None


def test_tab_session_mark_busy(tab_session: TabSession) -> None:
    tab_session.mark_busy("run-001")
    assert tab_session.state == SessionState.BUSY
    assert tab_session.current_run_id == "run-001"


def test_tab_session_mark_idle(tab_session: TabSession) -> None:
    tab_session.mark_busy("run-001")
    tab_session.mark_idle()
    assert tab_session.state == SessionState.IDLE
    assert tab_session.current_run_id is None


def test_tab_session_mark_degraded(tab_session: TabSession) -> None:
    tab_session.mark_degraded()
    assert tab_session.state == SessionState.DEGRADED


def test_tab_session_mark_crashed(tab_session: TabSession) -> None:
    tab_session.mark_crashed()
    assert tab_session.state == SessionState.CRASHED


@pytest.mark.asyncio
async def test_tab_session_close(tab_session: TabSession) -> None:
    await tab_session.close()
    assert tab_session.state == SessionState.CLOSED


@pytest.mark.asyncio
async def test_tab_session_ensure_alive(tab_session: TabSession) -> None:
    alive = await tab_session.ensure_alive()
    assert alive is True
    assert tab_session.state == SessionState.IDLE


@pytest.mark.asyncio
async def test_tab_session_ensure_alive_closed(tab_session: TabSession) -> None:
    await tab_session.close()
    alive = await tab_session.ensure_alive()
    assert alive is False


@pytest.mark.asyncio
async def test_tab_session_screenshot_debug(tab_session: TabSession) -> None:
    path = await tab_session.screenshot_debug("test_label")
    assert path is not None
    assert "test_label" in str(path)


@pytest.mark.asyncio
async def test_tab_session_get_url(tab_session: TabSession) -> None:
    url = await tab_session.get_url()
    assert url == "about:blank"


def test_tab_session_age_seconds(tab_session: TabSession) -> None:
    age = tab_session.age_seconds()
    assert age >= 0
    assert age < 5


def test_tab_session_idle_seconds(tab_session: TabSession) -> None:
    idle = tab_session.idle_seconds()
    assert idle >= 0


def test_tab_session_initial_state_enum_values() -> None:
    assert SessionState.IDLE.value == "IDLE"
    assert SessionState.BUSY.value == "BUSY"
    assert SessionState.DEGRADED.value == "DEGRADED"
    assert SessionState.CRASHED.value == "CRASHED"
    assert SessionState.CLOSED.value == "CLOSED"


def test_tab_session_repr(tab_session: TabSession) -> None:
    r = repr(tab_session)
    assert tab_session.session_id in r
    assert tab_session.provider_name in r
