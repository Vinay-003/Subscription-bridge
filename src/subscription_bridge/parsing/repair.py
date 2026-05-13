from __future__ import annotations

import re


def strip_code_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_first_json(text: str) -> str:
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
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


def unescape_newlines(text: str) -> str:
    return text.replace("\\n", "\n").replace("\\t", "\t")


def repair_json(text: str) -> str:
    text = strip_code_fences(text)
    text = extract_first_json(text)
    text = fix_trailing_commas(text)
    text = unescape_newlines(text)
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
