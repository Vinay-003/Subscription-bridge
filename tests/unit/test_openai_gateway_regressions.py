from __future__ import annotations

import json

from subscription_bridge.api.openai.message_converter import (
    BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT,
    _format_tools_for_prompt,
    convert_messages,
)
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
    raw = '{"tool_calls":[{"function":{"name":"unknown","arguments":{}}},{"function":{"name":"update_config","arguments":{"enabled":true,"retries":2,"ratio":1.0,"labels":[],"options":{},"content":"ok"}}}]}'
    calls = parse_tool_calls(raw, tools=[_tool()], tool_choice={"type": "function", "function": {"name": "update_config"}})
    assert len(calls) == 1
    assert calls[0].function.name == "update_config"


def test_tool_choice_none_disables_tool_parsing() -> None:
    raw = '{"name":"update_config","arguments":{"enabled":true,"retries":2,"ratio":1.0,"labels":[],"options":{},"content":"ok"}}'
    assert parse_tool_calls(raw, tools=[_tool()], tool_choice="none") == []


def test_malformed_typed_argument_is_rejected() -> None:
    raw = '{"name":"update_config","arguments":{"enabled":"perhaps","retries":"bad","ratio":"1.0","labels":"[]","options":"{}","content":"ok"}}'
    assert parse_tool_calls(raw, tools=[_tool()]) == []


def test_tool_schema_is_not_truncated() -> None:
    long_description = "x" * 1000
    tool = _tool()
    tool["function"]["parameters"]["properties"]["content"]["description"] = long_description
    formatted = _format_tools_for_prompt([tool])
    assert long_description in formatted
    assert '"properties"' in formatted


def test_browser_style_system_prompt_disallows_interactive_html() -> None:
    assert "plain text" in BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT
    assert "interactive widget" in BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT
    assert "HTML page" in BROWSER_RESPONSE_STYLE_SYSTEM_PROMPT


def test_converter_preserves_full_opencode_system_prompt_and_formats_tool_choice() -> None:
    full_system = "You are opencode. # Core Mandates\n" + ("Keep all instructions. " * 200)
    messages = [OpenAIMessage(role="system", content=full_system), OpenAIMessage(role="user", content="Do work")]
    _, system_prompt = convert_messages(
        messages,
        tools=[_tool()],
        tool_choice={"type": "function", "function": {"name": "update_config"}},
        require_json_tools=True,
    )
    assert full_system in system_prompt
    assert "MUST call only the tool named update_config" in system_prompt
    assert "BROWSER RESPONSE STYLE" in system_prompt


def test_conversation_id_does_not_change_as_tool_results_are_added() -> None:
    first = [
        OpenAIMessage(role="system", content="system instructions"),
        OpenAIMessage(role="user", content="Fix the app"),
    ]
    next_turn = first + [
        OpenAIMessage(role="assistant", content=None, tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": "{}"}}]),
        OpenAIMessage(role="tool", content="file contents", tool_call_id="call_1"),
    ]
    assert _conversation_id(first) == _conversation_id(next_turn)


def test_converter_keeps_tool_result_as_current_tail() -> None:
    messages = [
        OpenAIMessage(role="system", content="system instructions"),
        OpenAIMessage(role="user", content="Fix the app"),
        OpenAIMessage(role="assistant", content=None, tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": "{}"}}]),
        OpenAIMessage(role="tool", content="file contents", tool_call_id="call_1"),
    ]
    prompt, _ = convert_messages(messages)
    assert "file contents" in prompt
    assert "Fix the app" not in prompt  # the initial prompt is already browser history


def test_remote_image_guard_rejects_local_and_non_http_targets() -> None:
    from subscription_bridge.api.openai.message_converter import _is_public_http_url

    assert not _is_public_http_url("http://127.0.0.1:8000/private.png")
    assert not _is_public_http_url("http://169.254.169.254/latest/meta-data")
    assert not _is_public_http_url("http://localhost/image.png")
    assert not _is_public_http_url("file:///etc/passwd")
    assert not _is_public_http_url("http://user:password@example.com/image.png")
