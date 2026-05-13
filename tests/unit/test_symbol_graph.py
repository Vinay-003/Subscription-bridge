from __future__ import annotations

from pathlib import Path

from subscription_bridge.memory.symbol_graph import (
    build_symbol_index,
    extract_symbols_from_file,
)


def test_extract_python_functions(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("def foo():\n    pass\n\nasync def bar():\n    pass\n")
    symbols = extract_symbols_from_file(f)
    names = [s.name for s in symbols]
    assert "foo" in names
    assert "bar" in names


def test_extract_python_classes(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("class MyClass:\n    pass\n")
    symbols = extract_symbols_from_file(f)
    names = [s.name for s in symbols]
    assert "MyClass" in names


def test_extract_python_imports(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("import os\nfrom pathlib import Path, PurePath\n")
    symbols = extract_symbols_from_file(f)
    types = [s.symbol_type for s in symbols]
    assert "import" in types


def test_extract_js_functions(tmp_path: Path) -> None:
    f = tmp_path / "test.js"
    f.write_text("function greet(name) {\n  return name;\n}\n")
    symbols = extract_symbols_from_file(f)
    names = [s.name for s in symbols]
    assert "greet" in names


def test_extract_js_classes(tmp_path: Path) -> None:
    f = tmp_path / "test.js"
    f.write_text("class User {\n  constructor() {}\n}\n")
    symbols = extract_symbols_from_file(f)
    names = [s.name for s in symbols]
    assert "User" in names


def test_extract_ts_functions(tmp_path: Path) -> None:
    f = tmp_path / "test.ts"
    f.write_text("interface User {\n  name: string;\n}\n")
    symbols = extract_symbols_from_file(f)
    names = [s.name for s in symbols]
    assert "User" in names


def test_build_symbol_index() -> None:
    from subscription_bridge.memory.models import CodeSymbol
    symbols = [
        CodeSymbol(name="hello", symbol_type="function", file_path="test.py", line=1),
        CodeSymbol(name="world", symbol_type="class", file_path="test.py", line=5),
    ]
    index = build_symbol_index(symbols)
    assert "hello" in index
    assert "world" in index


def test_extract_from_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.py"
    f.write_text("")
    symbols = extract_symbols_from_file(f)
    assert symbols == []


def test_extract_from_binary_rejected(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02")
    symbols = extract_symbols_from_file(f)
    assert symbols == []
