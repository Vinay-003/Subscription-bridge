from __future__ import annotations

import pytest

from subscription_bridge.providers.base import ProviderRequest
from subscription_bridge.providers.fake import FakeProviderAdapter


@pytest.mark.asyncio
async def test_scripted_responses_in_order() -> None:
    provider = FakeProviderAdapter(scripted_responses=[
        '{"type":"tool_call","thought":"first","tool_name":"file_read","arguments":{"path":"x.txt"}}',
        '{"type":"final","thought":"second","answer":"done"}',
    ])
    req = ProviderRequest(run_id="t1", prompt="do it", require_json=True)

    r1 = await provider.send_prompt(req)
    assert r1.success
    assert '"tool_call"' in r1.text

    r2 = await provider.send_prompt(req)
    assert r2.success
    assert '"final"' in r2.text


@pytest.mark.asyncio
async def test_scripted_responses_repeat_last() -> None:
    provider = FakeProviderAdapter(scripted_responses=[
        '{"type":"final","thought":"only_one","answer":"done"}',
    ])
    req = ProviderRequest(run_id="t1", prompt="do it", require_json=True)

    r1 = await provider.send_prompt(req)
    r2 = await provider.send_prompt(req)
    assert r1.text == r2.text


@pytest.mark.asyncio
async def test_scripted_resets() -> None:
    provider = FakeProviderAdapter(scripted_responses=[
        '{"type":"tool_call","thought":"x","tool_name":"file_read","arguments":{"path":"x.txt"}}',
        '{"type":"final","thought":"y","answer":"done"}',
    ])
    req = ProviderRequest(run_id="t1", prompt="do it", require_json=True)

    await provider.send_prompt(req)
    r2 = await provider.send_prompt(req)
    assert '"final"' in r2.text

    provider.reset_script()
    r3 = await provider.send_prompt(req)
    assert '"tool_call"' in r3.text
