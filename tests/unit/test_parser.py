from __future__ import annotations

import pytest

from subscription_bridge.core.errors import ParserError
from subscription_bridge.parsing.json_parser import parse_agent_action
from subscription_bridge.parsing.repair import (
    build_repair_prompt,
    extract_first_json,
    fix_smart_quotes,
    fix_trailing_commas,
    repair_json,
    strip_code_fences,
)


def test_direct_tool_call() -> None:
    text = '{"type":"tool_call","thought":"need info","tool_name":"file_read","arguments":{"path":"test.txt"}}'
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_read"
    assert action.arguments == {"path": "test.txt"}
    assert action.thought == "need info"


def test_direct_final() -> None:
    text = '{"type":"final","thought":"done","answer":"The answer is 42"}'
    action = parse_agent_action(text)
    assert action.action_type == "final"
    assert action.answer == "The answer is 42"


def test_direct_clarification() -> None:
    text = '{"type":"ask_clarification","thought":"unclear","question":"Which file?"}'
    action = parse_agent_action(text)
    assert action.action_type == "ask_clarification"
    assert action.question == "Which file?"


def test_markdown_wrapped_json() -> None:
    text = "```json\n{\"type\":\"final\",\"thought\":\"done\",\"answer\":\"ok\"}\n```"
    action = parse_agent_action(text)
    assert action.action_type == "final"
    assert action.answer == "ok"


def test_text_before_after_json() -> None:
    text = 'Some preamble text {\"type\":\"final\",\"thought\":\"x\",\"answer\":\"y\"} trailing text'
    action = parse_agent_action(text)
    assert action.action_type == "final"
    assert action.answer == "y"


def test_trailing_comma_repair() -> None:
    text = '{"type":"final","thought":"x","answer":"y",}'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_trailing_comma_in_nested() -> None:
    text = '{"type":"tool_call","thought":"x","tool_name":"file_read","arguments":{"path":"test.txt",}}'
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"


def test_smart_quotes_repair() -> None:
    left = "\u201c"
    right = "\u201d"
    text = f"{left}type{right}: {left}final{right}"
    repaired = fix_smart_quotes(text)
    assert '"type"' in repaired
    assert '"final"' in repaired


def test_unexpected_type() -> None:
    text = '{"type":"invalid_type","thought":"x","answer":"y"}'
    with pytest.raises(ParserError, match="Unknown action type"):
        parse_agent_action(text)


def test_missing_tool_name() -> None:
    text = '{"type":"tool_call","thought":"x","arguments":{}}'
    with pytest.raises(ParserError, match="missing"):
        parse_agent_action(text)


def test_missing_answer() -> None:
    text = '{"type":"final","thought":"x"}'
    with pytest.raises(ParserError, match="missing"):
        parse_agent_action(text)


def test_missing_question() -> None:
    text = '{"type":"ask_clarification","thought":"x"}'
    with pytest.raises(ParserError, match="missing"):
        parse_agent_action(text)


def test_non_dict_json() -> None:
    text = '["tool_call", "file_read"]'
    with pytest.raises(ParserError, match="JSON object"):
        parse_agent_action(text)


def test_repair_single_quotes() -> None:
    text = "{'type': 'final', 'thought': 'x', 'answer': 'y'}"
    with pytest.raises(ParserError):
        parse_agent_action(text)


def test_regex_recovery_file_write_with_unescaped_quotes() -> None:
    text = (
        '{\n'
        '"type": "tool_call",\n'
        '"thought": "write calculator",\n'
        '"tool_name": "file_write",\n'
        '"arguments": {\n'
        '"path": "calculator.c",\n'
        '"content": "#include <stdio.h>\\nint main(){\\n    printf("Enter operator: ");\\n    return 0;\\n}"\n'
        '}\n'
        '}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    assert action.arguments["path"] == "calculator.c"
    assert 'printf("Enter operator: ");' in action.arguments["content"]


def test_regex_recovery_bash_command_with_unescaped_quotes() -> None:
    text = (
        '{\n'
        '"type": "tool_call",\n'
        '"tool_name": "bash",\n'
        '"arguments": {\n'
        '"command": "echo "int main(){" > a.c && echo "printf("hi");" >> a.c"\n'
        '}\n'
        '}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "bash"
    assert "echo \"int main(){\" > a.c" in action.arguments["command"]
    assert 'echo "printf("hi");" >> a.c' in action.arguments["command"]


def test_strip_code_fences() -> None:
    result = strip_code_fences("```json\n{\"key\": \"value\"}\n```")
    assert result == '{"key": "value"}'


def test_strip_code_fences_no_json() -> None:
    result = strip_code_fences("```\nhello\n```")
    assert result == "hello"


def test_extract_first_json_simple() -> None:
    result = extract_first_json('prefix {"a": 1} suffix')
    assert result == '{"a": 1}'


def test_extract_first_json_nested() -> None:
    result = extract_first_json('{"a": {"b": [1, 2]}}')
    assert result == '{"a": {"b": [1, 2]}}'


def test_fix_trailing_commas_in_object() -> None:
    result = fix_trailing_commas('{"a": 1,}')
    assert "}," not in result


def test_fix_smart_quotes() -> None:
    result = fix_smart_quotes('\u201chello\u201d')
    assert result == '"hello"'


def test_repair_json_full() -> None:
    text = "```\n{\"type\":\"final\",\"thought\":\"done\",\"answer\":\"ok\",}\n```"
    result = repair_json(text)
    assert '\\n' not in result
    assert ",}" not in result
    assert "```" not in result


def test_build_repair_prompt() -> None:
    prompt = build_repair_prompt("bad json", "parse error")
    assert "bad json" in prompt
    assert "parse error" in prompt
