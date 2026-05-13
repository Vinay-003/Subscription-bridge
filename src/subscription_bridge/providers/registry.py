from __future__ import annotations

import re
from typing import Any

from subscription_bridge.providers.base import ProviderAdapter, ProviderCapability
from subscription_bridge.utils.config import load_providers_config


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def get(self, name: str) -> ProviderAdapter:
        if name not in self._adapters:
            allowed = ", ".join(sorted(self._adapters.keys()))
            msg = f"Provider {name!r} not found. Available providers: {allowed}"
            raise KeyError(msg)
        return self._adapters[name]

    def list_providers(self) -> list[dict[str, Any]]:
        config = load_providers_config()
        provider_configs = config.get("providers", {})

        result: list[dict[str, Any]] = []
        for name, adapter in sorted(self._adapters.items()):
            cfg = provider_configs.get(name, {})
            result.append(
                {
                    "name": name,
                    "enabled": cfg.get("enabled", True),
                    "capabilities": sorted(adapter.capabilities),
                    "available": True,
                    "priority": cfg.get("priority", 100),
                }
            )
        return result

    def route(self, task: str) -> ProviderAdapter:
        config = load_providers_config()
        rules = config.get("routing", {}).get("rules", [])
        default_name = config.get("routing", {}).get("default_provider", "fake")

        for rule in rules:
            pattern = rule.get("task_pattern", "")
            provider_name = rule.get("provider", "")
            if provider_name in self._adapters and re.search(pattern, task, re.IGNORECASE):
                return self._adapters[provider_name]

        if default_name in self._adapters:
            return self._adapters[default_name]

        if self._adapters:
            return next(iter(self._adapters.values()))

        msg = "No providers registered"
        raise RuntimeError(msg)

    def get_providers_with_capability(self, capability: ProviderCapability) -> list[ProviderAdapter]:
        return [a for a in self._adapters.values() if capability in a.capabilities]

    @property
    def available_providers(self) -> list[str]:
        return sorted(self._adapters.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)
