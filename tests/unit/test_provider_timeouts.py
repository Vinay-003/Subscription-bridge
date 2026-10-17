from __future__ import annotations

from subscription_bridge.providers.timeouts import (
    DEFAULT_RESPONSE_WAIT_SECONDS,
    DEFAULT_SEND_CONFIRM_SECONDS,
    MAX_RESPONSE_WAIT_SECONDS,
    response_wait_seconds,
    send_confirm_seconds,
)


def test_floor_comes_from_selector_generation_config() -> None:
    # configs/selectors/*.yaml set timeouts.generation to 300000ms.
    assert response_wait_seconds("gemini") == DEFAULT_RESPONSE_WAIT_SECONDS
    assert response_wait_seconds("chatgpt") == DEFAULT_RESPONSE_WAIT_SECONDS


def test_unknown_provider_falls_back_to_default_floor() -> None:
    assert response_wait_seconds("claude") == DEFAULT_RESPONSE_WAIT_SECONDS


def test_requested_budget_below_floor_is_raised() -> None:
    assert response_wait_seconds("gemini", 30) == DEFAULT_RESPONSE_WAIT_SECONDS


def test_requested_budget_above_floor_is_honoured() -> None:
    assert response_wait_seconds("gemini", 655) == 655.0


def test_requested_budget_is_capped() -> None:
    assert response_wait_seconds("gemini", 5000) == MAX_RESPONSE_WAIT_SECONDS


def test_send_confirm_uses_selector_timeout() -> None:
    assert send_confirm_seconds("gemini") == DEFAULT_SEND_CONFIRM_SECONDS
    assert send_confirm_seconds("chatgpt") == DEFAULT_SEND_CONFIRM_SECONDS
