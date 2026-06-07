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


def _looks_like_json_key(text: str, start: int) -> bool:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != '"':
        return False
    key_end = text.find('"', start + 1)
    if key_end < 0 or key_end >= len(text) - 1:
        return False
    check = key_end + 1
    while check < len(text) and text[check].isspace():
        check += 1
    return check < len(text) and text[check] == ":"


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
                nxt_pos = -1
                for j in range(i + 1, min(len(text), i + 10)):
                    c = text[j]
                    if c not in " \t\n\r":
                        nxt = c
                        nxt_pos = j
                        break
                if nxt == "}":
                    check = nxt_pos + 1
                    while check < len(text) and text[check].isspace():
                        check += 1
                    if check >= len(text) or text[check] == ",":
                        in_string = False
                        result.append(ch)
                    elif text[check] == "}":
                        further = check + 1
                        while further < len(text) and text[further].isspace():
                            further += 1
                        if further >= len(text) or text[further] in (",", "}"):
                            in_string = False
                            result.append(ch)
                        else:
                            result.append('\\"')
                    else:
                        result.append('\\"')
                elif nxt == ",":
                    if nxt_pos >= 0 and _looks_like_json_key(text, nxt_pos + 1):
                        in_string = False
                        result.append(ch)
                    else:
                        result.append('\\"')
                elif nxt in ("]", ":"):
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
    """Find : '...' patterns and convert them to : \"...\" with inner dquotes escaped.
    Only operates outside double-quoted strings to avoid corrupting C-like content.
    """
    result: list[str] = []
    i = 0
    in_dq = False
    while i < len(text):
        if text[i] == "\\":
            result.append(text[i : i + 2])
            i += 2
            continue
        if text[i] == '"':
            in_dq = not in_dq
            result.append(text[i])
            i += 1
            continue
        if not in_dq:
            after_colon = text[i:].lstrip()
            if after_colon.startswith("'") and i > 0 and text[i - 1] in (":", " "):
                value_start = i + (len(text[i:]) - len(after_colon))
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
                continue
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
                ahead_pos = -1
                for j in range(i + 1, min(len(text), i + 8)):
                    c = text[j]
                    if c not in " \t\n\r":
                        ahead = c
                        ahead_pos = j
                        break
                if ahead == "]":
                    in_str = False
                    result.append(ch)
                elif ahead == "}":
                    check = ahead_pos + 1
                    while check < len(text) and text[check].isspace():
                        check += 1
                    if check >= len(text) or text[check] == ",":
                        in_str = False
                        result.append(ch)
                    elif text[check] == "}":
                        further = check + 1
                        while further < len(text) and text[further].isspace():
                            further += 1
                        if further >= len(text) or text[further] in (",", "}"):
                            in_str = False
                            result.append(ch)
                        else:
                            result.append('\\"')
                    else:
                        result.append('\\"')
                elif ahead == ",":
                    if ahead_pos >= 0 and _looks_like_json_key(text, ahead_pos + 1):
                        in_str = False
                        result.append(ch)
                    else:
                        result.append('\\"')
                elif ahead == ":":
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


def escape_unescaped_chars_in_strings(text: str) -> str:
    r"""Escape raw newlines, tabs, and carriage returns inside JSON string values.

    LLMs frequently emit invalid JSON with literal newlines inside string values
    (e.g. when the model pastes C source code into a JSON 'content' field without
    escaping the embedded \n). This function walks the text and escapes any
    unescaped control character that appears inside a double-quoted string.

    The escaping produces the 2-char sequence \n (backslash + n) in the JSON
    source, which JSON parses back to a real newline. This makes the JSON
    syntactically valid; downstream code that wants C-style escape semantics
    must apply fix_code_string_newlines() after JSON parsing.

    Rules:
    - The walker tracks whether we are inside a JSON string.
    - Inside a string, raw newline becomes \n (2 chars), raw CR becomes \r,
      raw tab becomes \t.
    - Backslashes that begin a valid escape sequence (\\, \", \/, \b, \f, \n, \r,
      \t, \u) are left untouched so we do not double-escape.
    - A raw " that ends the string is detected by the usual heuristic: followed
      by a JSON delimiter (',', '}', ']', ':' or whitespace + one of those).
    - Outside a string, the text is left untouched so JSON structure is preserved.
    """
    result: list[str] = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                if i + 1 < n and text[i + 1] in '"\\/bfnrtu':
                    result.append(ch)
                    result.append(text[i + 1])
                    i += 2
                    continue
                result.append("\\\\")
                i += 1
                continue
            if ch == '"':
                look = i + 1
                while look < n and text[look] in " \t\r\n":
                    look += 1
                if look < n and text[look] in (",", "}", "]", ":"):
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                result.append('\\"')
                i += 1
                continue
            if ch == "\n":
                result.append("\\n")
                i += 1
                continue
            if ch == "\r":
                result.append("\\r")
                i += 1
                continue
            if ch == "\t":
                result.append("\\t")
                i += 1
                continue
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def fix_code_string_newlines(text: str) -> str:
    r"""Convert raw newlines inside code string literals to the 2-char \n.

    After JSON parsing, the value of a 'content' / 'command' / 'replace' field
    contains the model's intended code as a string. LLMs sometimes leave raw
    newlines inside the code's own string literals where the C/Python/JS escape
    sequence \n was meant, e.g.:

        printf("%.2lf\n", x);   <-- C source as the model intended it
        printf("%.2lf           <-- what actually appears in the value when the
        ", x);                     model forgot to escape the newline

    The first form is valid C; the second is not, because C does not allow raw
    newlines inside string literals. This walker tracks code-level string state
    (inside "..." or '...') and converts raw newlines (and CR/tab) inside such
    literals to the 2-char escape sequence \n. Outside a code string literal,
    raw newlines are preserved so the C source still has line breaks.

    Notes / limitations:
    - Triple-quoted Python strings (three consecutive double quotes) are NOT
      supported as a single literal; the walker treats each pair of quotes
      independently. This is acceptable for the common case (C printf, Python
      f-strings, JS template literals are not handled but the walker degrades
      gracefully).
    - Existing 2-char escapes (\\, \", \n, \r, \t, etc.) inside the value are
      passed through untouched.
    - This is intentionally a post-processor applied to the *parsed* value,
      so it does not interfere with the JSON repair pipeline.
    """
    result: list[str] = []
    in_dq = False
    in_sq = False
    escape_next = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            i += 1
            continue
        if ch == '"' and not in_sq:
            in_dq = not in_dq
            result.append(ch)
            i += 1
            continue
        if ch == "'" and not in_dq:
            in_sq = not in_sq
            result.append(ch)
            i += 1
            continue
        if (in_dq or in_sq) and ch == "\n":
            result.append("\\n")
            i += 1
            continue
        if (in_dq or in_sq) and ch == "\r":
            result.append("\\r")
            i += 1
            continue
        if (in_dq or in_sq) and ch == "\t":
            result.append("\\t")
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def repair_json(text: str) -> str:
    text = strip_code_fences(text)
    text = extract_first_json(text)
    text = fix_trailing_commas(text)
    text = fix_smart_quotes(text)
    text = _convert_single_quoted_values(text)
    text = _replace_single_quotes(text)
    text = escape_unescaped_chars_in_strings(text)
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
