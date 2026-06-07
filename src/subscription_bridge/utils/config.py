from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_LOADED: bool = False
_CONFIG_CACHE: dict[str, Any] = {}
_CONFIG_DIRS = [
    Path.cwd() / "configs",
    Path(__file__).resolve().parent.parent.parent.parent / "configs",
]


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if not _ENV_LOADED:
        load_dotenv()
        _ENV_LOADED = True


def _find_config_path(name: str) -> Path | None:
    for config_dir in _CONFIG_DIRS:
        candidate = config_dir / name
        if candidate.exists():
            return candidate
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return dict(yaml.safe_load(f) or {})


def _merge_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    _ensure_env_loaded()

    level = os.environ.get("BRIDGE_LOG_LEVEL")
    fmt = os.environ.get("BRIDGE_LOG_FORMAT")
    if level or fmt:
        logging_config = dict(config.get("logging", {}) or {})
        if level:
            logging_config["level"] = level.upper()
        if fmt:
            logging_config["format"] = fmt.lower()
        config["logging"] = logging_config

    provider = os.environ.get("BRIDGE_DEFAULT_PROVIDER")
    if provider:
        app_config = dict(config.get("app", {}) or {})
        app_config["default_provider"] = provider
        config["app"] = app_config

    mode = os.environ.get("BRIDGE_BROWSER_MODE")
    cdp_url = os.environ.get("BRIDGE_CDP_URL")
    headless = os.environ.get("BRIDGE_HEADLESS")
    if mode or cdp_url or headless is not None:
        browser_config = dict(config.get("browser", {}) or {})
        if mode:
            browser_config["mode"] = mode.lower()
        if cdp_url:
            browser_config["cdp_url"] = cdp_url
        if headless is not None:
            browser_config["headless"] = headless.lower() == "true"
        config["browser"] = browser_config

    return config


def load_config(force_reload: bool = False) -> dict[str, Any]:
    if not force_reload and _CONFIG_CACHE:
        return _CONFIG_CACHE

    _ensure_env_loaded()
    config: dict[str, Any] = {}

    app_config_path = _find_config_path("app.yaml")
    if app_config_path:
        config.update(_load_yaml(app_config_path))

    config = _merge_env_overrides(config)

    _CONFIG_CACHE.clear()
    _CONFIG_CACHE.update(config)
    return _CONFIG_CACHE


def clear_config_cache() -> None:
    _CONFIG_CACHE.clear()


def load_providers_config() -> dict[str, Any]:
    path = _find_config_path("providers.yaml")
    if not path:
        return {"providers": {}}

    data = _load_yaml(path)
    return data


def load_models_config() -> dict[str, Any]:
    path = _find_config_path("models.yaml")
    if not path:
        return {"models": {}, "aliases": {}}

    data = _load_yaml(path)
    return data


def load_selector_config(provider_name: str) -> dict[str, Any]:
    path = _find_config_path(f"selectors/{provider_name}.yaml")
    if not path:
        return {"provider": provider_name, "selectors": {}}

    return _load_yaml(path)


def load_tool_permissions() -> dict[str, Any]:
    path = _find_config_path("tool_permissions.yaml")
    if not path:
        return {}
    return _load_yaml(path)


def get_env(key: str, default: str = "") -> str:
    _ensure_env_loaded()
    return os.environ.get(key, default)


def get_app_dir() -> Path:
    data_dir = get_env("BRIDGE_DATA_DIR", "~/.subscription-bridge")
    return Path(data_dir).expanduser().resolve()
