from __future__ import annotations

import pytest

from subscription_bridge.browser.selector_registry import SelectorRegistry


@pytest.fixture
def registry() -> SelectorRegistry:
    return SelectorRegistry()


def test_gemini_selector_loading(registry: SelectorRegistry) -> None:
    config = registry.load("gemini")
    assert config["provider"] == "gemini"


def test_gemini_composer_selectors(registry: SelectorRegistry) -> None:
    composers = registry.get_selectors("gemini", "composer")
    assert len(composers) >= 3
    assert any("contenteditable" in s for s in composers)


def test_gemini_response_selectors(registry: SelectorRegistry) -> None:
    selectors = registry.get_selectors("gemini", "response")
    assert len(selectors) >= 3


def test_gemini_progress_selectors(registry: SelectorRegistry) -> None:
    selectors = registry.get_selectors("gemini", "progress")
    assert len(selectors) >= 3


def test_gemini_unsafe_words(registry: SelectorRegistry) -> None:
    words = registry.get_unsafe_click_words("gemini")
    assert len(words) >= 5
    assert "share" in words
    assert "delete" in words


def test_gemini_url(registry: SelectorRegistry) -> None:
    url = registry.get_url("gemini")
    assert url == "https://gemini.google.com/app"


def test_validate_gemini_selectors(registry: SelectorRegistry) -> None:
    config = registry.load("gemini")
    issues = SelectorRegistry.validate_config_shape(config)
    assert issues == {}, f"Selector validation issues: {issues}"
