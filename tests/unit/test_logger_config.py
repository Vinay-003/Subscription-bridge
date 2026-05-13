from __future__ import annotations

import os

from subscription_bridge.logging.logger import _get_log_format, _get_log_level
from subscription_bridge.utils.config import clear_config_cache, load_config


def test_logger_config_has_logging_section() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    logging_config = config.get("logging", {})
    assert logging_config.get("level") == "INFO"
    assert logging_config.get("format") == "console"


def test_logger_level_default() -> None:
    clear_config_cache()
    if "BRIDGE_LOG_LEVEL" in os.environ:
        del os.environ["BRIDGE_LOG_LEVEL"]
    level = _get_log_level()
    assert level == "INFO"


def test_logger_format_default() -> None:
    clear_config_cache()
    if "BRIDGE_LOG_FORMAT" in os.environ:
        del os.environ["BRIDGE_LOG_FORMAT"]
    fmt = _get_log_format()
    assert fmt == "console"


def test_logger_level_env_override() -> None:
    clear_config_cache()
    os.environ["BRIDGE_LOG_LEVEL"] = "DEBUG"
    level = _get_log_level()
    del os.environ["BRIDGE_LOG_LEVEL"]
    assert level == "DEBUG"


def test_logger_format_env_override() -> None:
    clear_config_cache()
    os.environ["BRIDGE_LOG_FORMAT"] = "json"
    fmt = _get_log_format()
    del os.environ["BRIDGE_LOG_FORMAT"]
    assert fmt == "json"


def test_config_env_override_log_level() -> None:
    clear_config_cache()
    os.environ["BRIDGE_LOG_LEVEL"] = "WARNING"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_LOG_LEVEL"]
    logging_config = config.get("logging", {})
    assert logging_config["level"] == "WARNING"


def test_config_env_override_log_format() -> None:
    clear_config_cache()
    os.environ["BRIDGE_LOG_FORMAT"] = "json"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_LOG_FORMAT"]
    logging_config = config.get("logging", {})
    assert logging_config["format"] == "json"


def test_config_env_override_default_provider() -> None:
    clear_config_cache()
    os.environ["BRIDGE_DEFAULT_PROVIDER"] = "gemini"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_DEFAULT_PROVIDER"]
    app_config = config.get("app", {})
    assert app_config["default_provider"] == "gemini"
