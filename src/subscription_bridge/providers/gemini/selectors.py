from __future__ import annotations

from typing import Any

from subscription_bridge.browser.selector_registry import SelectorRegistry

_registry = SelectorRegistry()


def gemini_selectors() -> SelectorRegistry:
    return _registry


def get_selector(key: str) -> list[str]:
    return _registry.get_selectors("gemini", key)


def get_unsafe_words() -> list[str]:
    return _registry.get_unsafe_click_words("gemini")


def get_timeout(key: str, default: int = 30000) -> int:
    return _registry.get_timeout("gemini", key, default)


def gemini_url() -> str:
    return _registry.get_url("gemini")


def load_gemini_config() -> dict[str, Any]:
    return _registry.load("gemini")
