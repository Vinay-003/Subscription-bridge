from __future__ import annotations

from typing import Final

# Agent run lifecycle
RUN_STARTED: Final[str] = "run_started"
RUN_COMPLETED: Final[str] = "run_completed"
RUN_FAILED: Final[str] = "run_failed"

# Provider session lifecycle
PROVIDER_SESSION_CREATED: Final[str] = "provider_session_created"

# Prompt/response lifecycle
PROMPT_SENT: Final[str] = "prompt_sent"
RESPONSE_RECEIVED: Final[str] = "response_received"
PARSE_FAILED: Final[str] = "parse_failed"

# Tool execution lifecycle
TOOL_CALLED: Final[str] = "tool_called"
TOOL_COMPLETED: Final[str] = "tool_completed"

# Browser lifecycle
BROWSER_RECOVERED: Final[str] = "browser_recovered"

ALL_EVENTS: Final[list[str]] = [
    RUN_STARTED,
    RUN_COMPLETED,
    RUN_FAILED,
    PROVIDER_SESSION_CREATED,
    PROMPT_SENT,
    RESPONSE_RECEIVED,
    PARSE_FAILED,
    TOOL_CALLED,
    TOOL_COMPLETED,
    BROWSER_RECOVERED,
]
