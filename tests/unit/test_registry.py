from __future__ import annotations

import pytest

from subscription_bridge.providers.fake import FakeProviderAdapter
from subscription_bridge.providers.registry import ProviderRegistry


@pytest.fixture
def registry() -> ProviderRegistry:
    r = ProviderRegistry()
    r.register(FakeProviderAdapter())
    return r


def test_registry_register() -> None:
    registry = ProviderRegistry()
    adapter = FakeProviderAdapter()
    registry.register(adapter)
    assert "fake" in registry
    assert len(registry) == 1


def test_registry_unregister() -> None:
    registry = ProviderRegistry()
    adapter = FakeProviderAdapter()
    registry.register(adapter)
    registry.unregister("fake")
    assert "fake" not in registry
    assert len(registry) == 0


def test_registry_get(registry: ProviderRegistry) -> None:
    adapter = registry.get("fake")
    assert isinstance(adapter, FakeProviderAdapter)


def test_registry_get_not_found(registry: ProviderRegistry) -> None:
    with pytest.raises(KeyError, match="nonexistent"):
        registry.get("nonexistent")


def test_registry_list_providers(registry: ProviderRegistry) -> None:
    providers = registry.list_providers()
    assert len(providers) >= 1

    fake_config = next((p for p in providers if p["name"] == "fake"), None)
    assert fake_config is not None
    assert fake_config["name"] == "fake"
    assert fake_config["available"] is True
    assert "text_chat" in fake_config["capabilities"]


def test_registry_available_providers(registry: ProviderRegistry) -> None:
    available = registry.available_providers
    assert "fake" in available


def test_registry_route_default(registry: ProviderRegistry) -> None:
    adapter = registry.route("any task")
    assert isinstance(adapter, FakeProviderAdapter)


def test_registry_empty_route() -> None:
    registry = ProviderRegistry()
    with pytest.raises(RuntimeError, match="No providers registered"):
        registry.route("test")


def test_registry_get_providers_with_capability(registry: ProviderRegistry) -> None:
    providers = registry.get_providers_with_capability("text_chat")
    assert len(providers) == 1

    providers = registry.get_providers_with_capability("image_generation")
    assert len(providers) == 0


def test_registry_contains(registry: ProviderRegistry) -> None:
    assert "fake" in registry
    assert "nonexistent" not in registry


def test_registry_len(registry: ProviderRegistry) -> None:
    assert len(registry) >= 1


@pytest.mark.asyncio
async def test_registry_provider_works_through_registry(registry: ProviderRegistry) -> None:
    adapter = registry.get("fake")
    from subscription_bridge.providers.base import ProviderRequest

    request = ProviderRequest(run_id="test-registry", prompt="test")
    response = await adapter.send_prompt(request)
    assert response.success is True
