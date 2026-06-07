from __future__ import annotations

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


def test_model_catalog_loads_configured_aliases() -> None:
    from subscription_bridge.api.openai.model_catalog import context_limit_for_model, resolve_model_alias

    assert resolve_model_alias("gemini-2.0-flash") == "subscription-bridge-gemini-fast"
    assert context_limit_for_model("subscription-bridge-gemini-thinking") == 192000


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
    assert route.variant == "Gemini 3 Deep Think"
    assert provider_metadata("subscription-bridge-gemini-thinking") == {
        "gemini_model_variant": "Gemini 3 Deep Think",
        "chatgpt_model_variant": None,
    }
    assert prompt_with_model_hint("hello", "subscription-bridge-gemini-thinking").startswith(
        "[Model: Gemini 3 Deep Think]"
    )
    assert (await resolve_adapter("subscription-bridge-fake", AppDependencies())).name == "fake"


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
    assert choice["message"]["tool_calls"][0]["id"] == "call_1"
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


def test_v1_models_includes_tool_definitions(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    fake_model = next(m for m in data["data"] if m["id"] == "subscription-bridge-fake")
    assert fake_model["tools"] is not None
    assert len(fake_model["tools"]) >= 5
    tool_names = [t["function"]["name"] for t in fake_model["tools"]]
    assert "file_read" in tool_names
    assert "file_write" in tool_names
    assert "bash" in tool_names
    assert "grep" in tool_names
    assert "patch" in tool_names


def test_v1_models_tool_definitions_have_schemas(client: TestClient) -> None:
    response = client.get("/v1/models")
    data = response.json()
    fake_model = next(m for m in data["data"] if m["id"] == "subscription-bridge-fake")
    for tool_def in fake_model["tools"]:
        assert tool_def["type"] == "function"
        assert "function" in tool_def
        assert "name" in tool_def["function"]
        assert "description" in tool_def["function"]
        assert "parameters" in tool_def["function"]


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


def test_health_includes_models_and_tool_count(client: TestClient) -> None:
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
