from __future__ import annotations

import json

from subscription_bridge.api.openai.message_converter import convert_messages
from subscription_bridge.api.openai.tool_parser import parse_tool_calls
from subscription_bridge.api.openai_compat import _conversation_id
from subscription_bridge.api.openai_models import OpenAIMessage


def _tool(name: str = "update_config") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Update a configuration object",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "retries": {"type": "integer"},
                    "ratio": {"type": "number"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "options": {"type": "object", "properties": {"mode": {"type": "string"}}},
                    "content": {"type": "string"},
                },
                "required": ["enabled", "retries", "ratio", "labels", "options", "content"],
            },
        },
    }


def test_sentinel_parser_preserves_multiline_string_and_coerces_schema_types() -> None:
    text = (
        "<<<TOOLCALL:update_config>>>\n"
        "<<<ARG:enabled>>>\ntrue\n"
        "<<<ARG:retries>>>\n3\n"
        "<<<ARG:ratio>>>\n0.75\n"
        "<<<ARG:labels>>>\n[\"alpha\", \"beta\"]\n"
        "<<<ARG:options>>>\n{\"mode\": \"fast\"}\n"
        "<<<ARG:content>>>\n\nprint(\"hello\")\n\n"
        "<<<END>>>"
    )
    calls = parse_tool_calls(text, tools=[_tool()])

    assert len(calls) == 1
    args = json.loads(calls[0].function.arguments)
    assert args["enabled"] is True
    assert args["retries"] == 3
    assert args["ratio"] == 0.75
    assert args["labels"] == ["alpha", "beta"]
    assert args["options"] == {"mode": "fast"}
    assert args["content"] == "\nprint(\"hello\")\n"


def test_parser_drops_unknown_tool_names_and_honors_forced_tool() -> None:
    raw = (
        '{"tool_calls":[{"function":{"name":"unknown","arguments":{}}},'
        '{"function":{"name":"update_config","arguments":{"enabled":true,'
        '"retries":2,"ratio":1.0,"labels":[],"options":{},"content":"ok"}}}]}'
    )
    tool_choice = {"type": "function", "function": {"name": "update_config"}}
    calls = parse_tool_calls(raw, tools=[_tool()], tool_choice=tool_choice)
    assert len(calls) == 1
    assert calls[0].function.name == "update_config"


def test_tool_choice_none_disables_tool_parsing() -> None:
    raw = (
        '{"name":"update_config","arguments":{"enabled":true,'
        '"retries":2,"ratio":1.0,"labels":[],"options":{},"content":"ok"}}'
    )
    assert parse_tool_calls(raw, tools=[_tool()], tool_choice="none") == []


def test_malformed_typed_argument_is_rejected() -> None:
    raw = (
        '{"name":"update_config","arguments":{"enabled":"perhaps",'
        '"retries":"bad","ratio":"1.0","labels":"[]","options":"{}","content":"ok"}}'
    )
    assert parse_tool_calls(raw, tools=[_tool()]) == []


def test_json_tool_call_from_browser_llm_output() -> None:
    """Browser LLM emits JSON tool_calls as instructed by the converter."""
    raw = (
        '{"tool_calls": [{"function": {"name": "update_config", '
        '"arguments": {"enabled": true, "retries": 2, "ratio": 1.0, '
        '"labels": [], "options": {}, "content": "ok"}}}]}'
    )
    calls = parse_tool_calls(raw, tools=[_tool()])
    assert len(calls) == 1
    assert calls[0].function.name == "update_config"
    args = json.loads(calls[0].function.arguments)
    assert args["enabled"] is True
    assert args["content"] == "ok"


def test_converter_preserves_full_opencode_system_prompt_and_formats_tool_choice() -> None:
    full_system = "You are opencode. # Core Mandates\n" + ("Keep all instructions. " * 200).strip()
    messages = [OpenAIMessage(role="system", content=full_system), OpenAIMessage(role="user", content="Do work")]
    _, system_prompt = convert_messages(
        messages,
        tools=[_tool()],
        tool_choice={"type": "function", "function": {"name": "update_config"}},
        require_json_tools=True,
    )
    assert full_system in system_prompt
    assert "MUST call only the tool named 'update_config'" in system_prompt
    assert "tool_calls" in system_prompt


def test_conversation_id_does_not_change_as_tool_results_are_added() -> None:
    first = [
        OpenAIMessage(role="system", content="system instructions"),
        OpenAIMessage(role="user", content="Fix the app"),
    ]
    next_turn = first + [
        OpenAIMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "file_read", "arguments": "{}"},
            }],
        ),
        OpenAIMessage(role="tool", content="file contents", tool_call_id="call_1"),
    ]
    assert _conversation_id(first) == _conversation_id(next_turn)


def test_conversation_id_changes_when_model_changes() -> None:
    messages = [
        OpenAIMessage(role="system", content="system instructions"),
        OpenAIMessage(role="user", content="Fix the app"),
    ]
    chatgpt = _conversation_id(messages, model="subscription-bridge-chatgpt")
    gemini = _conversation_id(messages, model="subscription-bridge-gemini-flash")
    assert chatgpt != gemini


def test_strip_provider_prefix_handles_opencode_slash_form() -> None:
    from subscription_bridge.api.openai.model_catalog import strip_provider_prefix

    assert strip_provider_prefix("subscription-bridge/gemini-flash") == "gemini-flash"
    assert strip_provider_prefix("openai/some-model") == "some-model"
    assert strip_provider_prefix("subscription-bridge-gemini-flash") == "subscription-bridge-gemini-flash"
    assert strip_provider_prefix("subscription-bridge-chatgpt") == "subscription-bridge-chatgpt"
    assert strip_provider_prefix("gemini-flash") == "gemini-flash"


def test_converter_includes_full_conversation_history() -> None:
    messages = [
        OpenAIMessage(role="system", content="system instructions"),
        OpenAIMessage(role="user", content="Fix the app"),
        OpenAIMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "file_read", "arguments": "{}"},
            }],
        ),
        OpenAIMessage(role="tool", content="file contents", tool_call_id="call_1"),
    ]
    prompt, _ = convert_messages(messages)
    assert "Fix the app" in prompt
    assert "file contents" in prompt
    assert "file_read" in prompt


def test_remote_image_guard_rejects_local_and_non_http_targets() -> None:
    from subscription_bridge.api.openai.message_converter import _is_public_http_url

    assert not _is_public_http_url("http://127.0.0.1:8000/private.png")
    assert not _is_public_http_url("http://169.254.169.254/latest/meta-data")
    assert not _is_public_http_url("http://localhost/image.png")
    assert not _is_public_http_url("file:///etc/passwd")
    assert not _is_public_http_url("http://user:password@example.com/image.png")
