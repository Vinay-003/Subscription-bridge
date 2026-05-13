from __future__ import annotations

import pytest

from subscription_bridge.browser.selector_registry import SelectorRegistry


@pytest.fixture
def registry() -> SelectorRegistry:
    return SelectorRegistry()


def test_load_gemini(registry: SelectorRegistry) -> None:
    config = registry.load("gemini")
    assert config["provider"] == "gemini"
    assert "selectors" in config
    assert "composer" in config["selectors"]


def test_load_chatgpt(registry: SelectorRegistry) -> None:
    config = registry.load("chatgpt")
    assert config["provider"] == "chatgpt"
    assert "selectors" in config


def test_load_claude(registry: SelectorRegistry) -> None:
    config = registry.load("claude")
    assert config["provider"] == "claude"
    assert "selectors" in config


def test_load_invalid_provider(registry: SelectorRegistry) -> None:
    config = registry.load("nonexistent")
    assert config["provider"] == "nonexistent"
    assert config["selectors"] == {}


def test_get_selectors(registry: SelectorRegistry) -> None:
    composers = registry.get_selectors("gemini", "composer")
    assert len(composers) >= 3
    assert any("contenteditable" in s for s in composers)


def test_get_selectors_unknown_key(registry: SelectorRegistry) -> None:
    result = registry.get_selectors("gemini", "nonexistent_key")
    assert result == []


def test_get_unsafe_click_words(registry: SelectorRegistry) -> None:
    words = registry.get_unsafe_click_words("gemini")
    assert len(words) >= 5
    assert "share" in words
    assert "delete" in words


def test_get_unsafe_click_words_default(registry: SelectorRegistry) -> None:
    words = registry.get_unsafe_click_words("chatgpt")
    assert isinstance(words, list)


def test_get_timeout(registry: SelectorRegistry) -> None:
    timeout = registry.get_timeout("gemini", "default")
    assert timeout == 30000


def test_get_timeout_fallback(registry: SelectorRegistry) -> None:
    timeout = registry.get_timeout("gemini", "nonexistent", default=15000)
    assert timeout == 15000


def test_get_url(registry: SelectorRegistry) -> None:
    url = registry.get_url("gemini")
    assert "gemini.google.com" in url


def test_reload(registry: SelectorRegistry) -> None:
    registry.load("gemini")
    assert registry.is_loaded("gemini")

    config = registry.reload("gemini")
    assert config["provider"] == "gemini"


def test_list_loaded(registry: SelectorRegistry) -> None:
    registry.load("gemini")
    registry.load("chatgpt")
    loaded = registry.list_loaded()
    assert "gemini" in loaded
    assert "chatgpt" in loaded


def test_clear_cache(registry: SelectorRegistry) -> None:
    registry.load("gemini")
    assert registry.is_loaded("gemini")
    registry.clear_cache()
    assert not registry.is_loaded("gemini")


def test_validate_config_shape_valid(registry: SelectorRegistry) -> None:
    config = registry.load("gemini")
    issues = SelectorRegistry.validate_config_shape(config)
    assert issues == {}


def test_validate_config_shape_invalid() -> None:
    issues = SelectorRegistry.validate_config_shape(
        {"provider": "bad", "selectors": {"key": "not_a_list"}}
    )
    assert "selector_type" in issues


def test_get_timeout_from_nonexistent_provider(registry: SelectorRegistry) -> None:
    timeout = registry.get_timeout("nonexistent", "default")
    assert timeout == 30000
