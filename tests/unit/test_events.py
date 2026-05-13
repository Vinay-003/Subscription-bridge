from __future__ import annotations

from subscription_bridge.logging.events import (
    ALL_EVENTS,
    BROWSER_RECOVERED,
    PARSE_FAILED,
    PROMPT_SENT,
    PROVIDER_SESSION_CREATED,
    RESPONSE_RECEIVED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    TOOL_CALLED,
    TOOL_COMPLETED,
)


def test_all_events_defined() -> None:
    assert RUN_STARTED == "run_started"
    assert RUN_COMPLETED == "run_completed"
    assert RUN_FAILED == "run_failed"


def test_provider_events() -> None:
    assert PROVIDER_SESSION_CREATED == "provider_session_created"


def test_prompt_events() -> None:
    assert PROMPT_SENT == "prompt_sent"
    assert RESPONSE_RECEIVED == "response_received"
    assert PARSE_FAILED == "parse_failed"


def test_tool_events() -> None:
    assert TOOL_CALLED == "tool_called"
    assert TOOL_COMPLETED == "tool_completed"


def test_browser_events() -> None:
    assert BROWSER_RECOVERED == "browser_recovered"


def test_all_events_list() -> None:
    assert len(ALL_EVENTS) == 10
    assert RUN_STARTED in ALL_EVENTS
    assert BROWSER_RECOVERED in ALL_EVENTS


def test_all_events_no_duplicates() -> None:
    assert len(ALL_EVENTS) == len(set(ALL_EVENTS))
