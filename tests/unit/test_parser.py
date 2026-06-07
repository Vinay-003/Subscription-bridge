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


def test_create_plan() -> None:
    text = (
        '{"type":"create_plan","thought":"planning","plan_summary":"write calculator",'
        '"todos":[{"content":"create file","details":"write calculator.c"},{"content":"compile","details":""}]}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "create_plan"
    assert action.plan_summary == "write calculator"
    assert len(action.todos) == 2
    assert action.todos[0]["content"] == "create file"


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


def test_unexpected_type_falls_to_plain_text() -> None:
    text = '{"type":"invalid_type","thought":"x","answer":"y"}'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_missing_tool_name_falls_to_plain_text() -> None:
    text = '{"type":"tool_call","thought":"x","arguments":{}}'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_missing_answer_falls_to_plain_text() -> None:
    text = '{"type":"final","thought":"x"}'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_missing_question_falls_to_plain_text() -> None:
    text = '{"type":"ask_clarification","thought":"x"}'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_non_dict_json_falls_to_plain_text() -> None:
    text = '["tool_call", "file_read"]'
    action = parse_agent_action(text)
    assert action.action_type == "final"


def test_repair_single_quotes_plain_text_fallback() -> None:
    text = "{'type': 'final', 'thought': 'x', 'answer': 'y'}"
    action = parse_agent_action(text)
    assert action.action_type == "final"


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


def test_openai_tool_calls_format() -> None:
    text = (
        '{"tool_calls":[{"id":"call_1","type":"function",'
        '"function":{"name":"file_read","arguments":{"path":"test.txt"}}}]}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_read"
    assert action.arguments == {"path": "test.txt"}


def test_openai_tool_calls_arguments_as_json_string() -> None:
    text = (
        '{"tool_calls": [{"id": "call_1", "type": "function", '
        '"function": {"name": "file_write", '
        '"arguments": "{\\"path\\": \\"a.txt\\", \\"content\\": \\"hi\\"}"}}]}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    assert action.arguments == {"path": "a.txt", "content": "hi"}


def test_alternative_action_input_format() -> None:
    text = '{"action":"file_read","action_input":{"path":"test.txt"}}'
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_read"
    assert action.arguments == {"path": "test.txt"}


def test_arguments_as_json_string() -> None:
    text = (
        '{"type":"tool_call","tool_name":"file_write",'
        '"arguments":"{\\"path\\": \\"a.txt\\", \\"content\\": \\"hello\\"}"}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    assert action.arguments == {"path": "a.txt", "content": "hello"}


def test_args_as_pythonish_dict_string() -> None:
    text = (
        "{\"type\":\"tool_call\",\"tool_name\":\"file_write\","
        "\"arguments\": \"{'path': 'a.txt', 'content': 'hello'}\"}"
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    assert action.arguments == {"path": "a.txt", "content": "hello"}


def test_c_source_content_in_file_write() -> None:
    text = (
        '{"type":"tool_call","tool_name":"file_write",'
        '"arguments":{"path":"calc.c","content":"#include <stdio.h>\\n'
        'int main() {\\n    printf(\\"Hello\\\\n\\");\\n    return 0;\\n}"}}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    assert 'printf(' in action.arguments["content"]


def test_raw_newlines_in_file_write_content_are_escaped() -> None:
    """Model emits invalid JSON with raw newlines inside string values.

    The C-aware post-processor must convert raw newlines that appear *inside*
    a C string literal (between two double quotes) into the 2-char \\n
    sequence, while preserving real newlines that are *line breaks* in the C
    source. This is the difference between a compilable C file and a broken
    one.
    """
    text = (
        '{\n'
        '"type": "tool_call",\n'
        '"tool_name": "file_write",\n'
        '"arguments": {\n'
        '"path": "calc.c",\n'
        '"content": "#include <stdio.h>\n\nint main() {\n    printf(\\"hi\\n\\");\n    return 0;\n}"\n'
        '}\n'
        '}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    content = action.arguments["content"]
    assert 'printf("hi\\n");' in content, repr(content)
    assert 'int main() {' in content
    assert '    return 0;' in content
    assert content.count("\\n") == 1, f"only the printf escape should be 2-char, got: {repr(content)}"
    assert content.count("\n") >= 5, "line breaks should be preserved as real newlines"


def test_raw_newline_in_c_calculator_compiles() -> None:
    """End-to-end: a typical Gemini-style broken JSON tool call for a C file
    with raw newlines inside the content string must produce compilable C
    source (the raw newlines get escaped to the literal two-char sequence)."""
    import subprocess
    import tempfile
    from pathlib import Path

    text = (
        '{\n'
        '"type": "tool_call",\n'
        '"tool_name": "file_write",\n'
        '"arguments": {\n'
        '"path": "calc.c",\n'
        '"content": "#include <stdio.h>\n\nint main() {\n'
        '    int a, b;\n'
        '    scanf(\\"%d %d\\", &a, &b);\n'
        '    printf(\\"%d\\n\\", a + b);\n'
        '    return 0;\n}"\n'
        '}\n'
        '}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "calc.c"
        path.write_text(action.arguments["content"], encoding="utf-8")
        result = subprocess.run(
            ["gcc", "-c", str(path), "-o", str(path.with_suffix(".o"))],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, f"C source did not compile:\n{result.stderr}"


def test_repair_escapes_raw_newlines_in_json_strings() -> None:
    from subscription_bridge.parsing.repair import repair_json

    text = (
        '{"type":"tool_call","tool_name":"file_write",'
        '"arguments":{"path":"a.c","content":"int main(){\nreturn 0;\n}"}}'
    )
    repaired = repair_json(text)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed["arguments"]["content"] == "int main(){\nreturn 0;\n}"


def test_broken_gemini_calculator_compiles_and_runs() -> None:
    """End-to-end test: a typical broken Gemini output with raw newlines
    inside printf string literals must be reparsed into a compilable,
    runnable C calculator.

    This mirrors the real failure mode reported in the wild: the model
    emits a JSON tool call but forgets to escape newlines that should
    have been the 2-char \\n inside a C string literal. The post-processor
    in the parser must distinguish 'line break' newlines (preserve as-is)
    from 'C string literal' newlines (convert to 2-char \\n) so the
    resulting C source is valid and the calculator runs correctly.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    text = (
        '{\n'
        '  "type": "tool_call",\n'
        '  "tool_name": "file_write",\n'
        '  "arguments": {\n'
        '    "path": "calculator.c",\n'
        '    "content": "#include <stdio.h>\\n\\nint main() {\\n'
        '    char op;\\n'
        '    double a, b;\\n'
        '    scanf(\\"%lf %lf\\", &a, &b);\\n'
        '    printf(\\"sum = %.2lf\\n\\", a + b);\\n'
        '    return 0;\\n}"\n'
        '  }\n'
        '}'
    )
    action = parse_agent_action(text)
    assert action.action_type == "tool_call"
    assert action.tool_name == "file_write"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "calculator.c"
        path.write_bytes(action.arguments["content"].encode("utf-8"))
        bin_path = Path(td) / "calculator"
        result = subprocess.run(
            ["gcc", str(path), "-o", str(bin_path), "-lm"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, f"C source did not compile:\n{result.stderr}"
        run = subprocess.run(
            [str(bin_path)], input="2.5 4.0\n",
            capture_output=True, text=True, check=False,
        )
        assert run.returncode == 0
        assert "6.50" in run.stdout


def test_plain_text_final_fallback() -> None:
    text = "I have created the file successfully."
    action = parse_agent_action(text)
    assert action.action_type == "final"
    assert action.answer == text


def test_empty_text_raises_error() -> None:
    with pytest.raises(ParserError, match="Cannot parse"):
        parse_agent_action("")


def test_whitespace_only_raises_error() -> None:
    with pytest.raises(ParserError):
        parse_agent_action("   \n  \t  ")


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
