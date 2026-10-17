from __future__ import annotations

import json

from subscription_bridge.api.openai.tool_parser import parse_tool_calls
from subscription_bridge.browser.ui_guard import default_unsafe_words


def test_tool_parser_normalizes_aliases_and_required_bash_description():
    tools = [{
        "type": "function",
        "function": {
            "name": "bash",
            "description": "run",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}, "description": {"type": "string"}},
                "required": ["command", "description"],
            },
        },
    }]
    calls = parse_tool_calls('<<< TOOLCALL: run_command >>>\n<<<ARG:command>>> echo hi\n<<<END>>>', tools=tools)
    assert len(calls) == 1
    assert calls[0].function.name == "bash"
    args = json.loads(calls[0].function.arguments)
    assert args["command"] == "echo hi"
    assert args["description"]


def test_sentinel_parser_accepts_inline_values_and_missing_end_marker():
    tools = [{
        "type": "function",
        "function": {
            "name": "read",
            "parameters": {
                "type": "object",
                "properties": {"filePath": {"type": "string"}},
                "required": ["filePath"],
            },
        },
    }]
    calls = parse_tool_calls('Copy code\n<<< TOOLCALL: read >>><<<ARG:filePath>>> /tmp/a.txt', tools=tools)
    assert len(calls) == 1
    assert json.loads(calls[0].function.arguments) == {"filePath": "/tmp/a.txt"}


def test_json_package_manifest_is_not_a_tool_call():
    assert parse_tool_calls('{"name":"package.json","version":"1.0.0"}') == []


def test_new_chat_is_not_globally_blocked_by_ui_guard():
    assert "new chat" not in default_unsafe_words()


def test_opencode_system_prompt_passes_through_unmodified():
    from types import SimpleNamespace

    from subscription_bridge.api.openai.message_converter import convert_messages

    full_system = "You are opencode\n# Core Mandates\n<env><cwd>/tmp/project</cwd></env>"
    messages = [
        SimpleNamespace(role="system", content=full_system),
        SimpleNamespace(role="user", content="hi", tool_calls=None, tool_call_id=None),
    ]
    _, system_prompt = convert_messages(messages)
    assert system_prompt == full_system


def test_tool_results_are_not_truncated_at_one_thousand_characters():
    from types import SimpleNamespace

    from subscription_bridge.api.openai.message_converter import convert_messages

    large = "x" * 1500
    messages = [
        SimpleNamespace(role="user", content="read file", tool_calls=None, tool_call_id=None),
        SimpleNamespace(
            role="assistant",
            content=None,
            tool_calls=[{"function": {"name": "read", "arguments": "{}"}}],
            tool_call_id=None,
        ),
        SimpleNamespace(role="tool", content=large, tool_calls=None, tool_call_id="call_1"),
    ]
    prompt, _ = convert_messages(messages, full_history=True)
    assert large in prompt


def test_request_accepts_nullable_and_new_openai_fields():
    from subscription_bridge.api.openai_models import ChatCompletionRequest

    request = ChatCompletionRequest(
        model="test", messages=[{"role": "user", "content": "hi"}],
        temperature=None, max_tokens=None, max_completion_tokens=1200,
        stream_options={"include_usage": True}, parallel_tool_calls=False,
        response_format={"type": "json_object"}, reasoning_effort="low",
    )
    assert request.temperature is None and request.max_tokens is None
    assert request.max_completion_tokens == 1200
    assert request.stream_options["include_usage"] is True
