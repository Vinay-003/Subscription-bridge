from __future__ import annotations

from subscription_bridge.utils.config import (
    get_env,
    load_config,
    load_providers_config,
    load_selector_config,
    load_tool_permissions,
)


def test_load_config() -> None:
    config = load_config(force_reload=True)
    assert isinstance(config, dict)
    assert "app" in config


def test_load_config_has_app_name() -> None:
    config = load_config(force_reload=True)
    app_config = config.get("app", {})
    assert app_config.get("name") == "SubscriptionBridge"


def test_load_providers_config() -> None:
    config = load_providers_config()
    assert "providers" in config
    assert "fake" in config["providers"]
    assert "gemini" in config["providers"]


def test_load_selector_config_gemini() -> None:
    config = load_selector_config("gemini")
    assert config["provider"] == "gemini"
    assert "selectors" in config
    assert "composer" in config["selectors"]


def test_load_selector_config_chatgpt() -> None:
    config = load_selector_config("chatgpt")
    assert config["provider"] == "chatgpt"
    assert "selectors" in config


def test_load_selector_config_not_found() -> None:
    config = load_selector_config("nonexistent")
    assert config["provider"] == "nonexistent"
    assert config["selectors"] == {}


def test_load_tool_permissions() -> None:
    config = load_tool_permissions()
    assert isinstance(config, dict)
    assert "file_read" in config
    assert "bash" in config


def test_tool_permissions_has_deny_commands() -> None:
    config = load_tool_permissions()
    bash_config = config.get("bash", {})
    deny = bash_config.get("deny_commands", [])
    assert "rm -rf /" in deny
    assert "shutdown" in deny


def test_get_env_default() -> None:
    value = get_env("NONEXISTENT_ENV_VAR", "default_value")
    assert value == "default_value"


def test_get_env_actual() -> None:
    import os

    os.environ["TEST_BRIDGE_VAR"] = "test_value"
    value = get_env("TEST_BRIDGE_VAR", "default")
    assert value == "test_value"
    del os.environ["TEST_BRIDGE_VAR"]
