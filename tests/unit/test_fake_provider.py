from __future__ import annotations

import pytest

from subscription_bridge.providers.base import ProviderCapability, ProviderRequest
from subscription_bridge.providers.fake import FakeProviderAdapter


@pytest.fixture
def fake_provider() -> FakeProviderAdapter:
    return FakeProviderAdapter()


@pytest.mark.asyncio
async def test_fake_provider_name(fake_provider: FakeProviderAdapter) -> None:
    assert fake_provider.name == "fake"


@pytest.mark.asyncio
async def test_fake_provider_capabilities(fake_provider: FakeProviderAdapter) -> None:
    assert "text_chat" in fake_provider.capabilities
    assert "code_reasoning" in fake_provider.capabilities


@pytest.mark.asyncio
async def test_fake_provider_create_session(fake_provider: FakeProviderAdapter) -> None:
    session_id = await fake_provider.create_session()
    assert session_id.startswith("fake-")
    assert len(session_id) > 10


@pytest.mark.asyncio
async def test_fake_provider_send_prompt(fake_provider: FakeProviderAdapter) -> None:
    request = ProviderRequest(
        run_id="test-001",
        prompt="Hello, world!",
    )
    response = await fake_provider.send_prompt(request)
    assert response.success is True
    assert response.provider == "fake"
    assert response.text != ""
    assert response.latency_seconds >= 0


@pytest.mark.asyncio
async def test_fake_provider_json_response(fake_provider: FakeProviderAdapter) -> None:
    request = ProviderRequest(
        run_id="test-002",
        prompt="Return JSON with project_name",
        require_json=True,
    )
    response = await fake_provider.send_prompt(request)
    assert response.success is True
    import json

    parsed = json.loads(response.text)
    assert parsed["type"] == "final"
    assert "answer" in parsed


@pytest.mark.asyncio
async def test_fake_provider_health_check(fake_provider: FakeProviderAdapter) -> None:
    ok = await fake_provider.health_check()
    assert ok is True


@pytest.mark.asyncio
async def test_fake_provider_failure_rate() -> None:
    provider = FakeProviderAdapter(fail_rate=1.0)
    request = ProviderRequest(run_id="test-003", prompt="This will fail")
    response = await provider.send_prompt(request)
    assert response.success is False
    assert response.error == "Simulated provider failure"


@pytest.mark.asyncio
async def test_fake_provider_session_lifecycle(fake_provider: FakeProviderAdapter) -> None:
    session_id = await fake_provider.create_session()
    assert session_id in fake_provider.active_sessions

    await fake_provider.close_session(session_id)
    assert session_id not in fake_provider.active_sessions


@pytest.mark.asyncio
async def test_fake_provider_reset_chat(fake_provider: FakeProviderAdapter) -> None:
    await fake_provider.reset_chat("test-session")
    await fake_provider.reset_chat("all")


@pytest.mark.asyncio
async def test_fake_provider_capabilities_enum() -> None:
    expected: set[ProviderCapability] = {"text_chat", "code_reasoning"}
    assert FakeProviderAdapter.capabilities == expected
