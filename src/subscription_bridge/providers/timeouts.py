from __future__ import annotations

from subscription_bridge.browser.selector_registry import SelectorRegistry

_registry = SelectorRegistry()

DEFAULT_RESPONSE_WAIT_SECONDS = 300.0
MAX_RESPONSE_WAIT_SECONDS = 900.0
DEFAULT_SEND_CONFIRM_SECONDS = 35.0


def response_wait_seconds(provider: str, requested_seconds: float | None = None) -> float:
    """Resolve how long a provider waits for the browser to finish answering.

    ``timeouts.generation`` in the provider's selector config is the floor, so
    slow models (Argon/Pro with thinking) are never cut off after a short
    default. A client-supplied budget derived from its max token request may
    raise the wait above the floor, up to a hard cap so a runaway generation
    cannot pin a browser tab indefinitely.
    """
    configured = _registry.get_timeout(
        provider, "generation", int(DEFAULT_RESPONSE_WAIT_SECONDS * 1000)
    )
    floor = configured / 1000.0 if configured > 0 else DEFAULT_RESPONSE_WAIT_SECONDS
    requested = float(requested_seconds) if requested_seconds else floor
    return min(max(requested, floor), MAX_RESPONSE_WAIT_SECONDS)


def send_confirm_seconds(provider: str) -> float:
    """Resolve the full send-confirmation wait; callers use a shorter first try."""
    configured = _registry.get_timeout(
        provider, "send_confirm", int(DEFAULT_SEND_CONFIRM_SECONDS * 1000)
    )
    return configured / 1000.0 if configured > 0 else DEFAULT_SEND_CONFIRM_SECONDS
