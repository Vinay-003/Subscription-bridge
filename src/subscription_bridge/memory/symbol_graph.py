from __future__ import annotations

import ast
import re
from pathlib import Path

from subscription_bridge.memory.chunker import detect_language
from subscription_bridge.memory.models import CodeSymbol


def extract_symbols_from_file(file_path: Path) -> list[CodeSymbol]:
    lang = detect_language(file_path)
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    if lang == "python":
        return _extract_python(text, str(file_path))
    if lang in ("javascript", "typescript"):
        return _extract_js_ts(text, str(file_path), lang)
    return _extract_regex(text, str(file_path), lang)


def _extract_python(text: str, file_path: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _extract_regex(text, file_path, "python")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(CodeSymbol(
                name=node.name,
                symbol_type="function",
                file_path=file_path,
                line=node.lineno,
            ))
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(CodeSymbol(
                name=node.name,
                symbol_type="function",
                file_path=file_path,
                line=node.lineno,
            ))
        elif isinstance(node, ast.ClassDef):
            symbols.append(CodeSymbol(
                name=node.name,
                symbol_type="class",
                file_path=file_path,
                line=node.lineno,
            ))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id.isupper():
                        symbols.append(CodeSymbol(
                            name=target.id,
                            symbol_type="constant",
                            file_path=file_path,
                            line=node.lineno,
                        ))

    _extract_python_imports(text, file_path, symbols)
    return symbols


def _extract_python_imports(text: str, file_path: str, symbols: list[CodeSymbol]) -> None:
    for match in re.finditer(r"^\s*import\s+(\S+)", text, re.MULTILINE):
        symbols.append(CodeSymbol(
            name=match.group(1),
            symbol_type="import",
            file_path=file_path,
            line=text[:match.start()].count("\n") + 1,
        ))
    for match in re.finditer(r"^\s*from\s+(\S+)\s+import\s+(\S+)", text, re.MULTILINE):
        parent = match.group(1)
        for name in re.split(r"\s*,\s*", match.group(2)):
            name = name.strip()
            if name and name != "*":
                symbols.append(CodeSymbol(
                    name=name,
                    symbol_type="import",
                    file_path=file_path,
                    line=text[:match.start()].count("\n") + 1,
                    parent=parent,
                ))


def _extract_js_ts(text: str, file_path: str, lang: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    patterns = [
        (r"(?:export\s+)?(?:function\s+|async\s+function\s+)(\w+)", "function"),
        (r"(?:export\s+)?class\s+(\w+)", "class"),
        (r"(?:export\s+)?interface\s+(\w+)", "interface"),
        (r"(?:export\s+)?type\s+(\w+)\s*=", "type"),
        (r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", "function"),
        (r"(?:const|let|var)\s+(\w+)\s*=\s*function", "function"),
    ]
    for pattern, sym_type in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            symbols.append(CodeSymbol(
                name=match.group(1),
                symbol_type=sym_type,
                file_path=file_path,
                line=text[:match.start()].count("\n") + 1,
            ))

    for match in re.finditer(
        r'(?:import\s+.*?\s+from\s+[\'"](\S+)[\'"]|require\s*\(\s*[\'"](\S+)[\'"]\s*\))',
        text,
    ):
        name = match.group(1) or match.group(2)
        symbols.append(CodeSymbol(
            name=name,
            symbol_type="import",
            file_path=file_path,
            line=text[:match.start()].count("\n") + 1,
        ))

    return symbols


def _extract_regex(text: str, file_path: str, lang: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []
    patterns = [
        (r"(?:def\s+|fn\s+|func\s+|function\s+)(\w+)", "function"),
        (r"class\s+(\w+)", "class"),
    ]
    for pattern, sym_type in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            symbols.append(CodeSymbol(
                name=match.group(1),
                symbol_type=sym_type,
                file_path=file_path,
                line=text[:match.start()].count("\n") + 1,
            ))
    return symbols


def build_symbol_index(symbols: list[CodeSymbol]) -> dict[str, list[CodeSymbol]]:
    index: dict[str, list[CodeSymbol]] = {}
    for sym in symbols:
        key = sym.name.lower()
        index.setdefault(key, []).append(sym)
        for part in re.split(r"[._]", sym.name):
            if part and len(part) > 2:
                index.setdefault(part.lower(), []).append(sym)
    return index
