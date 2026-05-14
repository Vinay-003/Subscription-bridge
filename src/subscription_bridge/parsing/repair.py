from __future__ import annotations

import json
import re


def strip_code_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_first_json(text: str) -> str:
    brace_depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if start == -1:
                start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start != -1:
                return text[start : i + 1]
    if start != -1:
        return text[start:]
    return text


def fix_trailing_commas(text: str) -> str:
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*\]", "]", text)
    return text


def fix_smart_quotes(text: str) -> str:
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u00ab": '"',
        "\u00bb": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def escape_json_string(text: str) -> str:
    result: list[str] = []
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                nxt = ""
                for j in range(i + 1, min(len(text), i + 10)):
                    c = text[j]
                    if c not in " \t\n\r":
                        nxt = c
                        break
                if nxt in (",", "}", "]", ":"):
                    in_string = False
                    result.append(ch)
                else:
                    result.append('\\"')
            continue
        if in_string and ch in "\n\r\t":
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            continue
        result.append(ch)
    return "".join(result)


def _convert_single_quoted_values(text: str) -> str:
    """Find : '...' patterns and convert them to : \"...\" with inner dquotes escaped."""
    result: list[str] = []
    i = 0
    while i < len(text):
        after_colon = text[i:].lstrip()
        if after_colon.startswith("'") and i > 0 and text[i - 1] in (":", " "):
            value_start = i + (len(after_colon) - len(text[i:]))
            result.append(text[i:value_start])
            result.append('"')
            j = value_start + 1
            while j < len(text):
                if text[j] == "\\":
                    result.append(text[j:j+2])
                    j += 2
                    continue
                if text[j] == "'":
                    result.append('"')
                    j += 1
                    break
                if text[j] == '"':
                    result.append('\\"')
                    j += 1
                    continue
                result.append(text[j])
                j += 1
            i = j
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _replace_single_quotes(text: str) -> str:
    in_string = False
    in_single = False
    escape_next = False
    result: list[str] = []
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            in_single = False
            result.append(ch)
            continue
        if ch == "'":
            if not in_string:
                in_string = True
                in_single = True
                result.append('"')
            elif in_single:
                in_string = False
                in_single = False
                result.append('"')
            else:
                result.append("'")
            continue
        result.append(ch)
    return "".join(result)


def try_parse_action_input(text: str) -> dict[str, str] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            text_fixed = text.replace("'", '"')
            text_fixed = text_fixed.replace("None", "null").replace("True", "true").replace("False", "false")
            data = json.loads(text_fixed)
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(data, dict):
        return data
    return None


def _escape_dquotes_aggressive(text: str) -> str:
    result: list[str] = []
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            result.append(ch)
            esc = False
            continue
        if ch == "\\":
            result.append(ch)
            esc = True
            continue
        if ch == '"':
            if not in_str:
                in_str = True
                result.append(ch)
            else:
                ahead = ""
                for j in range(i + 1, min(len(text), i + 8)):
                    c = text[j]
                    if c not in " \t\n\r":
                        ahead = c
                        break
                if ahead in (",", "}", "]", ":"):
                    in_str = False
                    result.append(ch)
                elif ahead == "":
                    in_str = False
                    result.append(ch)
                else:
                    result.append('\\"')
            continue
        result.append(ch)
    return "".join(result)


def repair_json(text: str) -> str:
    text = strip_code_fences(text)
    text = extract_first_json(text)
    text = fix_trailing_commas(text)
    text = fix_smart_quotes(text)
    text = _convert_single_quoted_values(text)
    text = _replace_single_quotes(text)
    text = escape_json_string(text)
    text = _escape_dquotes_aggressive(text)
    return text.strip()


def build_repair_prompt(raw_text: str, error: str) -> str:
    return (
        "Your previous response was not valid JSON.\n"
        f"Error: {error}\n\n"
        f"Your raw response was:\n{raw_text}\n\n"
        "Please reformat your response as valid JSON matching the expected schema.\n"
        "Do not add commentary. Do not use Markdown fences.\n"
        "Return ONLY the JSON object."
    )
