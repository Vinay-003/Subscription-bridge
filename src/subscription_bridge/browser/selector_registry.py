from __future__ import annotations

from typing import Any

from subscription_bridge.utils.config import load_selector_config


class SelectorLoadError(Exception):
    ...


class SelectorRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, provider_name: str) -> dict[str, Any]:
        if provider_name in self._cache:
            return self._cache[provider_name]

        config = load_selector_config(provider_name)
        self._validate(config, provider_name)
        self._cache[provider_name] = config
        return config

    def reload(self, provider_name: str) -> dict[str, Any]:
        self._cache.pop(provider_name, None)
        return self.load(provider_name)

    def get_selectors(self, provider_name: str, key: str) -> list[str]:
        config = self.load(provider_name)
        selectors = config.get("selectors", {})
        raw = selectors.get(key, [])
        if isinstance(raw, list):
            return [str(s) for s in raw]
        if isinstance(raw, str):
            return [raw]
        return []

    def get_unsafe_click_words(self, provider_name: str) -> list[str]:
        config = self.load(provider_name)
        raw = config.get("unsafe_click_words", [])
        if isinstance(raw, list):
            return [str(w) for w in raw]
        return []

    def get_timeout(self, provider_name: str, key: str, default: int = 30000) -> int:
        config = self.load(provider_name)
        timeouts = config.get("timeouts", {})
        raw = timeouts.get(key, default)
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default

    def get_url(self, provider_name: str) -> str:
        config = self.load(provider_name)
        return str(config.get("url", ""))

    def is_loaded(self, provider_name: str) -> bool:
        return provider_name in self._cache

    def clear_cache(self) -> None:
        self._cache.clear()

    def list_loaded(self) -> list[str]:
        return list(self._cache.keys())

    @staticmethod
    def _validate(config: dict[str, Any], provider_name: str) -> None:
        errors: list[str] = []

        actual_provider = config.get("provider")
        if not actual_provider:
            errors.append(f"Missing 'provider' field in selector config for {provider_name!r}")

        selectors = config.get("selectors")
        if not isinstance(selectors, dict):
            errors.append(f"Missing or invalid 'selectors' dict in selector config for {provider_name!r}")

        if errors:
            msg = "; ".join(errors)
            raise SelectorLoadError(msg)

    @staticmethod
    def validate_config_shape(config: dict[str, Any]) -> dict[str, list[str]]:
        issues: dict[str, list[str]] = {}
        provider = config.get("provider", "<unknown>")

        selectors = config.get("selectors", {})
        for key, value in selectors.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if not isinstance(sub_value, list):
                        issues.setdefault("selector_type", []).append(
                            f"{provider}/{key}/{sub_key}: expected list, got {type(sub_value).__name__}"
                        )
            elif not isinstance(value, list):
                issues.setdefault("selector_type", []).append(
                    f"{provider}/{key}: expected list, got {type(value).__name__}"
                )

        unsafe = config.get("unsafe_click_words", [])
        if isinstance(unsafe, list):
            for item in unsafe:
                if not isinstance(item, str):
                    issues.setdefault("unsafe_word_type", []).append(
                        f"{provider}: expected string, got {type(item).__name__}"
                    )

        return issues
