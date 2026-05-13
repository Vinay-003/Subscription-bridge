from __future__ import annotations

from pathlib import Path

from subscription_bridge.memory.chunker import (
    chunk_file,
    detect_language,
    extract_imports,
    extract_symbols,
    is_binary,
    skip_dir,
)


def test_detect_language_python() -> None:
    assert detect_language("file.py") == "python"


def test_detect_language_markdown() -> None:
    assert detect_language("README.md") == "markdown"


def test_detect_language_unknown() -> None:
    assert detect_language("file.xyz") == "text"


def test_skip_dir() -> None:
    assert skip_dir(".git") is True
    assert skip_dir("node_modules") is True
    assert skip_dir("__pycache__") is True
    assert skip_dir("src") is False
    assert skip_dir("tests") is False


def test_is_binary_known_ext(tmp_path: Path) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"fake png")
    assert is_binary(f) is True


def test_is_binary_text(tmp_path: Path) -> None:
    f = tmp_path / "hello.py"
    f.write_text("print('hello')")
    assert is_binary(f) is False


def test_chunk_basic_text(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    lines = "\n".join(f"line {i}" for i in range(50))
    f.write_text(lines)
    chunks = chunk_file(f, tmp_path, max_lines=20, overlap=5)
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[1].start_line <= 21  # overlap


def test_chunk_symbol_extraction(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("def hello():\n    pass\n\nclass World:\n    pass\n")
    chunks = chunk_file(f, tmp_path, max_lines=20, overlap=5)
    assert len(chunks) >= 1
    assert "hello" in chunks[0].symbols or "World" in chunks[0].symbols


def test_chunk_import_extraction(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("import os\nfrom pathlib import Path\n")
    chunks = chunk_file(f, tmp_path, max_lines=20, overlap=5)
    assert len(chunks) >= 1
    assert "os" in chunks[0].imports
    assert "pathlib" in chunks[0].imports


def test_chunk_binary_skipped(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02")
    chunks = chunk_file(f, tmp_path)
    assert len(chunks) == 0


def test_chunk_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.py"
    f.write_text("")
    chunks = chunk_file(f, tmp_path)
    assert len(chunks) == 0


def test_chunk_very_large_file_skipped(tmp_path: Path) -> None:
    f = tmp_path / "huge.py"
    from subscription_bridge.memory.chunker import MAX_FILE_BYTES
    f.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    chunks = chunk_file(f, tmp_path)
    assert len(chunks) == 0


def test_extract_symbols_python() -> None:
    text = "def foo():\n    pass\nclass Bar:\n    pass\n"
    syms = extract_symbols(text, "python")
    assert "foo" in syms
    assert "Bar" in syms


def test_extract_imports_python() -> None:
    text = "import os\nfrom pathlib import Path\n"
    imps = extract_imports(text, "python")
    assert "os" in imps
    assert "pathlib" in imps
