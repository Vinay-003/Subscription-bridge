from __future__ import annotations

import os

from subscription_bridge.utils.config import clear_config_cache, load_config


def test_browser_config_default_mode() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    browser = config.get("browser", {})
    mode = browser.get("mode", "")
    assert mode in ("managed", "cdp"), f"Expected mode 'managed' or 'cdp', got '{mode}'"


def test_browser_config_default_cdp_url() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    browser = config.get("browser", {})
    cdp_url = browser.get("cdp_url", "")
    assert "127.0.0.1" in cdp_url
    assert "9333" in cdp_url
    assert "9222" not in cdp_url


def test_browser_config_max_sessions() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    browser = config.get("browser", {})
    assert browser.get("max_sessions") == 3


def test_browser_config_has_dirs() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    browser = config.get("browser", {})
    assert "user_data_dir" in browser
    assert "downloads_dir" in browser
    assert "debug_dir" in browser


def test_browser_config_env_override_mode() -> None:
    clear_config_cache()
    os.environ["BRIDGE_BROWSER_MODE"] = "cdp"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_BROWSER_MODE"]
    browser = config.get("browser", {})
    assert browser.get("mode") == "cdp"


def test_browser_config_env_override_cdp_url() -> None:
    clear_config_cache()
    os.environ["BRIDGE_CDP_URL"] = "http://127.0.0.1:9999"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_CDP_URL"]
    browser = config.get("browser", {})
    assert browser.get("cdp_url") == "http://127.0.0.1:9999"


def test_browser_config_env_override_headless() -> None:
    clear_config_cache()
    os.environ["BRIDGE_HEADLESS"] = "true"
    config = load_config(force_reload=True)
    del os.environ["BRIDGE_HEADLESS"]
    browser = config.get("browser", {})
    assert browser.get("headless") is True


def test_browser_config_no_port_9222() -> None:
    clear_config_cache()
    config = load_config(force_reload=True)
    yaml_text = open("configs/app.yaml").read()
    assert "9222" not in yaml_text, "Port 9222 must not appear in app.yaml"

    env_text = open(".env.example").read()
    assert "9222" not in env_text, "Port 9222 must not appear in .env.example"

    browser = config.get("browser", {})
    cdp_url = str(browser.get("cdp_url", ""))
    assert "9222" not in cdp_url, f"Port 9222 must not be in cdp_url config: {cdp_url}"
