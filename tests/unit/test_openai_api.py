from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from subscription_bridge.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_v1_models(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    model_ids = [m["id"] for m in data["data"]]
    assert "subscription-bridge-fake" in model_ids
    # Models advertise context_window so any OpenAI client can budget tokens/compaction.
    flash = next(m for m in data["data"] if m["id"] == "subscription-bridge-gemini-flash")
    assert flash["context_window"] == 1048576
    assert flash["reasoning"] is True


def test_model_catalog_loads_configured_aliases() -> None:
    from subscription_bridge.api.openai.model_catalog import context_limit_for_model, resolve_model_alias

    assert resolve_model_alias("gemini-2.0-flash") == "subscription-bridge-gemini-flash-lite"
    assert resolve_model_alias("subscription-bridge-gemini-fast") == "subscription-bridge-gemini-flash"
    assert context_limit_for_model("subscription-bridge-gemini-thinking") == 1000000
    assert context_limit_for_model("subscription-bridge-gemini-flash") == 1048576


def test_model_context_and_output_limits_match_published_specs() -> None:
    from subscription_bridge.api.openai.model_catalog import (
        context_limit_for_model,
        output_limit_for_model,
    )

    gemini_full = (
        "subscription-bridge-gemini-flash-lite",
        "subscription-bridge-gemini-flash",
    )
    for gemini_id in gemini_full:
        assert context_limit_for_model(gemini_id) == 1048576
        assert output_limit_for_model(gemini_id) == 65536

    assert context_limit_for_model("subscription-bridge-gemini-pro") == 1000000
    assert output_limit_for_model("subscription-bridge-gemini-pro") == 65536

    # Argon shares one 1,048,576 window across input/thinking/output, so the
    # usable input budget is the total minus the reserved output headroom.
    assert context_limit_for_model("subscription-bridge-gemini-argon") == 1048576 - 65536
    assert output_limit_for_model("subscription-bridge-gemini-argon") == 65536

    for chatgpt_id in (
        "subscription-bridge-chatgpt",
        "subscription-bridge-chatgpt-thinking",
        "subscription-bridge-chatgpt-pro",
    ):
        assert context_limit_for_model(chatgpt_id) == 128000
        assert output_limit_for_model(chatgpt_id) == 8192


def test_build_models_emits_context_window_and_reasoning() -> None:
    from subscription_bridge.api.openai.model_catalog import build_models

    models = {m.id: m for m in build_models()}
    flash = models["subscription-bridge-gemini-flash"]
    assert flash.context_window == 1048576
    assert flash.max_output_tokens == 65536
    assert flash.reasoning is True
    assert flash.reasoning_efforts == ["low", "medium", "high"]

    fake = models["subscription-bridge-fake"]
    assert fake.context_window == 32000
    assert fake.reasoning is False
    assert fake.reasoning_efforts == []


def test_reasoning_levels_for_model_defaults_and_overrides() -> None:
    from subscription_bridge.api.openai.model_catalog import reasoning_levels_for_model

    assert reasoning_levels_for_model("subscription-bridge-gemini-pro") == ["low", "medium", "high"]
    assert reasoning_levels_for_model("subscription-bridge-fake") == []


@pytest.mark.asyncio
async def test_model_router_resolves_provider_details() -> None:
    from subscription_bridge.api.dependencies import AppDependencies
    from subscription_bridge.api.openai.model_router import (
        prompt_with_model_hint,
        provider_metadata,
        resolve_adapter,
        route_for_model,
    )

    route = route_for_model("subscription-bridge-gemini-thinking")

    assert route is not None
    assert route.provider == "gemini"
    assert route.variant == "3.1 Pro"
    assert provider_metadata("subscription-bridge-gemini-thinking") == {
        "gemini_model_variant": "3.1 Pro",
        "chatgpt_model_variant": None,
    }
    assert prompt_with_model_hint("hello", "subscription-bridge-gemini-thinking") == "hello"  # no-op: transparent proxy
    assert (await resolve_adapter("subscription-bridge-fake", AppDependencies())).name == "fake"


def test_delta_messages_detects_history_rewrite() -> None:
    from subscription_bridge.api.openai_compat import _conversation_delta, _delta_messages
    from subscription_bridge.api.openai_models import OpenAIMessage

    conv = "test-conv-rewrite"
    _conversation_delta.pop(conv, None)
    m1 = [
        OpenAIMessage(role="system", content="sys"),
        OpenAIMessage(role="user", content="u1"),
    ]

    delta, rewritten = _delta_messages(m1, conv)
    assert delta == m1
    assert rewritten is False

    m2 = m1 + [
        OpenAIMessage(role="assistant", content="a1"),
        OpenAIMessage(role="user", content="u2"),
    ]
    delta, rewritten = _delta_messages(m2, conv)
    assert delta == m2[2:]
    assert rewritten is False

    # Client compacted history: message count shrank -> full resend + restart.
    m3 = [
        OpenAIMessage(role="system", content="sys"),
        OpenAIMessage(role="user", content="u1"),
        OpenAIMessage(role="user", content="summary"),
    ]
    delta, rewritten = _delta_messages(m3, conv)
    assert delta == m3
    assert rewritten is True

    delta, rewritten = _delta_messages(m2, conv)
    assert delta == m2[3:]
    assert rewritten is False
    _conversation_delta.pop(conv, None)


def test_normalize_thinking_level() -> None:
    from subscription_bridge.api.openai_compat import _normalize_thinking_level

    assert _normalize_thinking_level("low") == "low"
    assert _normalize_thinking_level("MEDIUM") == "medium"
    assert _normalize_thinking_level("high") == "high"
    assert _normalize_thinking_level("minimal") == "low"
    assert _normalize_thinking_level("none") == "low"
    assert _normalize_thinking_level("xhigh") == "high"
    assert _normalize_thinking_level("max") == "high"
    assert _normalize_thinking_level("weird") is None
    assert _normalize_thinking_level(None) is None


def test_chat_completions_wires_delta_restart_and_thinking_metadata(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from subscription_bridge.api import openai_compat as oc
    from subscription_bridge.providers.base import ProviderResponse

    captured: list[object] = []

    class CaptureAdapter:
        name = "fake"

        async def send_prompt(self, request: object) -> ProviderResponse:
            captured.append(request)
            return ProviderResponse(
                provider="fake", text="ok", raw_text="ok", success=True, latency_seconds=0.0,
            )

    async def fake_resolve(model_id: str, deps: object) -> CaptureAdapter:
        return CaptureAdapter()

    monkeypatch.setattr(oc, "resolve_adapter", fake_resolve)

    url = "/v1/chat/completions"
    headers = {"x-opencode-session": "sess-openai-wiring-test"}
    base = [
        {"role": "system", "content": "You are a coder."},
        {"role": "user", "content": "hello world"},
    ]

    r1 = client.post(
        url,
        json={"model": "subscription-bridge-fake", "messages": base, "reasoning_effort": "high"},
        headers=headers,
    )
    assert r1.status_code == 200
    req1 = captured[-1]
    assert req1.metadata["thinking_level"] == "high"
    assert "restart_conversation" not in req1.metadata
    assert "You are a coder." in req1.system_prompt
    assert req1.prompt == "User: hello world"
    assert req1.metadata["full_prompt"] == "User: hello world"

    extended = base + [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "second"},
    ]
    r2 = client.post(
        url,
        json={
            "model": "subscription-bridge-fake",
            "messages": extended,
            "reasoningEffort": "medium",
        },
        headers=headers,
    )
    assert r2.status_code == 200
    req2 = captured[-1]
    assert req2.prompt == "Assistant: hi\nUser: second"
    assert req2.system_prompt is None
    assert req2.metadata["thinking_level"] == "medium"
    assert req2.metadata["full_prompt"] == "User: hello world\nAssistant: hi\nUser: second"
    assert "restart_conversation" not in req2.metadata

    compacted = [
        {"role": "system", "content": "You are a coder."},
        {"role": "user", "content": "hello world"},
        {"role": "user", "content": "summary of everything so far"},
    ]
    r3 = client.post(
        url,
        json={"model": "subscription-bridge-fake", "messages": compacted},
        headers=headers,
    )
    assert r3.status_code == 200
    req3 = captured[-1]
    assert req3.metadata["restart_conversation"] is True
    assert "You are a coder." in req3.system_prompt
    assert req3.prompt == "User: hello world\nUser: summary of everything so far"
    assert "thinking_level" not in req3.metadata


# ── Tool call parsing tests ──────────────────────────────────────────────────


def test_parse_tool_calls_xml_tags() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = '<tool_call>{"name": "read_file", "arguments": {"path": "foo.py"}}</tool_call>'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "read_file"
    assert calls[0].function.arguments == '{"path": "foo.py"}'


def test_parse_tool_calls_extracted_module() -> None:
    from subscription_bridge.api.openai.tool_parser import parse_tool_calls

    text = '{"tool_calls":[{"function":{"name":"bash","arguments":{"command":"pwd"}}}]}'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "bash"
    assert calls[0].function.arguments == '{"command": "pwd"}'


def test_parse_tool_calls_multiple_xml() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = (
        '<tool_call>{"name": "read_file", "arguments": {"path": "a.py"}}</tool_call>\n'
        '<tool_call>{"name": "grep", "arguments": {"pattern": "test"}}</tool_call>'
    )
    calls = _parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0].function.name == "read_file"
    assert calls[1].function.name == "grep"


def test_parse_tool_calls_with_id_and_type() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = (
        '<tool_call>{"id": "call_1", "type": "function", '
        '"function": {"name": "bash", "arguments": {"command": "ls"}}}</tool_call>'
    )
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].id == "call_1"
    assert calls[0].type == "function"
    assert calls[0].function.name == "bash"
    assert calls[0].function.arguments == '{"command": "ls"}'


def test_parse_tool_calls_no_tools() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    calls = _parse_tool_calls("Hello, I am a helpful assistant.")
    assert calls == []


def test_parse_tool_calls_empty() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    assert _parse_tool_calls("") == []


def test_parse_tool_calls_malformed_json() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = '<tool_call>{"name": "read_file", "arguments": {"path"}}</tool_call>'
    calls = _parse_tool_calls(text)
    assert calls == []


def test_parse_tool_calls_code_block_fallback() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = '```json\n{"name": "bash", "arguments": {"command": "pwd"}}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].function.name == "bash"


def test_parse_tool_calls_arguments_as_object() -> None:
    from subscription_bridge.api.openai_compat import _parse_tool_calls

    text = '<tool_call>{"name": "write_file", "arguments": {"path": "x.py", "content": "print(1)"}}</tool_call>'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    import json
    args = json.loads(calls[0].function.arguments)
    assert args["path"] == "x.py"
    assert args["content"] == "print(1)"


def test_v1_unknown_model(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-unknown",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "not found" in data["error"]["message"].lower()


def test_v1_missing_messages(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "subscription-bridge-fake"},
    )
    assert response.status_code in (200, 422)


def test_v1_streaming(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Stream a greeting"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    text = response.text
    assert "data: [DONE]" in text
    assert "chat.completion.chunk" in text


def test_v1_usage_in_response(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    data = response.json()
    assert "usage" in data
    assert "prompt_tokens" in data["usage"]
    assert "completion_tokens" in data["usage"]
    assert "total_tokens" in data["usage"]


def test_v1_native_ask_still_works(client: TestClient) -> None:
    response = client.post(
        "/ask",
        json={"provider": "fake", "prompt": "hello"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_v1_native_run_still_works(client: TestClient) -> None:
    response = client.post(
        "/run",
        json={"provider": "fake", "task": "test task", "max_steps": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data


def test_native_agent_runs_endpoint(client: TestClient) -> None:
    response = client.post(
        "/agent/runs",
        json={"provider": "fake", "task": "test task", "max_steps": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "status" in data


def test_v1_chat_completion_accepts_workspace(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "hello"}],
            "workspace": "/tmp",
        },
    )
    assert response.status_code == 200


def test_v1_title_generator_short_circuit(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a title generator. You output ONLY a thread title.",
                },
                {"role": "user", "content": "sup"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"]


def test_v1_workspace_from_body(client: TestClient, tmp_path) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "hello"}],
            "workspace": str(tmp_path),
        },
    )
    assert response.status_code == 200


def test_v1_tools_accepted_without_execution(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Use tools"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] is not None


def test_v1_tools_returns_openai_tool_calls(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from subscription_bridge.providers.base import ProviderRequest, ProviderResponse

    class BrowserLikeProvider:
        name = "gemini"

        async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
            text = '{"tool_calls":[{"function":{"name":"file_read","arguments":{"path":"README.md"}}}]}'
            return ProviderResponse(
                provider=self.name,
                text=text,
                raw_text=text,
                success=True,
                latency_seconds=0.0,
            )

    async def resolve_adapter(model_id: str, deps: object) -> BrowserLikeProvider:
        return BrowserLikeProvider()

    monkeypatch.setattr("subscription_bridge.api.openai_compat._resolve_adapter", resolve_adapter)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-gemini-fast",
            "messages": [{"role": "user", "content": "Read README.md"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "file_read",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    choice = data["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    assert choice["message"]["tool_calls"][0]["id"].startswith("call_")
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "file_read"


def test_v1_tools_does_not_start_hidden_agent(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from subscription_bridge.providers.base import ProviderRequest, ProviderResponse

    class BrowserLikeProvider:
        name = "gemini"

        async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse(
                provider=self.name,
                text="Plain model answer",
                raw_text="Plain model answer",
                success=True,
                latency_seconds=0.0,
            )

    class ExplodingAgentRuntime:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("OpenAI compatibility endpoint must not start AgentRuntime")

    async def resolve_adapter(model_id: str, deps: object) -> BrowserLikeProvider:
        return BrowserLikeProvider()

    monkeypatch.setattr("subscription_bridge.api.openai_compat._resolve_adapter", resolve_adapter)
    monkeypatch.setattr("subscription_bridge.core.AgentRuntime", ExplodingAgentRuntime)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-gemini-fast",
            "messages": [{"role": "user", "content": "Use tools if needed"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "file_read",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["choices"][0]["message"]["content"] == "Plain model answer"


# ── Phase 9: Model catalog tool definitions ─────────────────────────────────


def test_v1_models_does_not_advertise_bridge_native_tools(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    fake_model = next(m for m in data["data"] if m["id"] == "subscription-bridge-fake")
    assert "tools" not in fake_model



def test_build_native_tool_definitions_all_have_parameters() -> None:
    from subscription_bridge.api.openai.model_catalog import build_native_tool_definitions

    defs = build_native_tool_definitions()
    assert len(defs) == 10
    for d in defs:
        assert d["type"] == "function"
        assert isinstance(d["function"]["parameters"], dict)


# ── Phase 9: Streaming for all providers ────────────────────────────────────


def test_v1_streaming_works_for_fake_provider(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "no-cache" in response.headers.get("cache-control", "")
    lines = [line for line in response.text.splitlines() if line.startswith("data:")]
    assert len(lines) >= 2
    assert lines[-1] == "data: [DONE]"


def test_v1_streaming_has_role_chunk(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )
    lines = [line for line in response.text.splitlines() if line.startswith("data:") and line != "data: [DONE]"]
    import json as _json
    first_chunk = _json.loads(lines[0].removeprefix("data: "))
    assert first_chunk["choices"][0]["delta"]["role"] == "assistant"


def test_v1_streaming_with_tools_parses_tool_calls(client: TestClient) -> None:
    import json as _json
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "file_read",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data:") and line != "data: [DONE]"]
    chunks = [_json.loads(line.removeprefix("data: ")) for line in lines]
    finish_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert len(finish_chunks) == 1


# ── Phase 9: Health endpoint enrichment ─────────────────────────────────────


def test_health_includes_models_and_tool_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mock provider health so the unit test does not touch a live browser/CDP.
    async def fake_healths(self: object) -> dict[str, str]:
        return {"fake": "ready", "gemini": "ready", "chatgpt": "ready"}

    from subscription_bridge.api import dependencies

    monkeypatch.setattr(
        dependencies.AppDependencies,
        "get_provider_healths",
        fake_healths,
    )
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "tool_count" in data
    assert "native_agent" in data
    assert len(data["models"]) >= 1
    assert "subscription-bridge-fake" in data["models"]
    assert data["tool_count"] >= 5
    assert data["native_agent"] is True



def test_openai_gateway_tool_loop_preserves_session_and_returns_to_opencode(
    monkeypatch: pytest.MonkeyPatch, client: TestClient,
) -> None:
    from subscription_bridge.providers.base import ProviderRequest, ProviderResponse

    seen: list[ProviderRequest] = []

    class ScriptedBrowserProvider:
        name = "gemini"

        async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
            seen.append(request)
            if len(seen) == 1:
                text = '<<<TOOLCALL:file_read>>>\n<<<ARG:path>>>\nREADME.md\n<<<END>>>'
            else:
                text = "Read result acknowledged."
            return ProviderResponse(
                provider=self.name, text=text, raw_text=text, success=True, latency_seconds=0.0,
            )

    async def resolve_adapter(model_id: str, deps: object) -> ScriptedBrowserProvider:
        return ScriptedBrowserProvider()

    monkeypatch.setattr("subscription_bridge.api.openai_compat._resolve_adapter", resolve_adapter)

    headers = {"x-opencode-session": "open-code-test-session"}
    tool = {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a file from the workspace",
            "parameters": {
                "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
            },
        },
    }
    initial = [
        {"role": "system", "content": "Keep the complete OpenCode system instructions."},
        {"role": "user", "content": "Inspect README.md and summarize it."},
    ]

    first = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={"model": "subscription-bridge-gemini-fast", "messages": initial, "tools": [tool]},
    )
    assert first.status_code == 200
    first_choice = first.json()["choices"][0]
    assert first_choice["finish_reason"] == "tool_calls"
    call = first_choice["message"]["tool_calls"][0]
    assert call["function"]["name"] == "file_read"
    assert json.loads(call["function"]["arguments"]) == {"path": "README.md"}

    second = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={
            "model": "subscription-bridge-gemini-fast",
            "messages": initial + [
                {"role": "assistant", "content": None, "tool_calls": [call]},
                {"role": "tool", "tool_call_id": call["id"], "content": "README contents"},
            ],
            "tools": [tool],
        },
    )
    assert second.status_code == 200
    assert second.json()["choices"][0]["message"]["content"] == "Read result acknowledged."
    assert len(seen) == 2
    assert seen[0].run_id == seen[1].run_id
    assert seen[0].metadata["isolated_conversation"] is True
    assert "README contents" in seen[1].prompt
    assert "Inspect README.md" not in seen[1].prompt  # delta: only new messages are sent
