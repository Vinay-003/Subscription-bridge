from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from subscription_bridge.memory.models import DocumentChunk

DEFAULT_MAX_LINES = 160
DEFAULT_OVERLAP = 20
MAX_FILE_BYTES = 500_000

_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".o", ".a", ".lib",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".ttf", ".otf",
}

_SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".subscription_bridge", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".egg-info", ".tox",
    ".idea", ".vscode", ".sixth",
}

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".sh": "bash",
    ".bash": "bash",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".txt": "text",
    ".cfg": "text",
    ".ini": "text",
}

_DEFINITION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),
        re.compile(r"^\s*class\s+(\w+)"),
    ],
    "javascript": [
        re.compile(r"(?:function\s+(\w+)\s*\()"),
        re.compile(r"(?:const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"),
        re.compile(r"(?:class\s+(\w+))"),
    ],
    "typescript": [
        re.compile(r"(?:function\s+(\w+)\s*\()"),
        re.compile(r"(?:const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"),
        re.compile(r"(?:class\s+(\w+))"),
        re.compile(r"(?:interface\s+(\w+))"),
        re.compile(r"(?:type\s+(\w+)\s*=)"),
    ],
}

_IMPORT_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"^\s*import\s+(\S+)"),
        re.compile(r"^\s*from\s+(\S+)\s+import"),
    ],
    "javascript": [
        re.compile(r"import\s+.*?\s+from\s+['\"](\S+)['\"]"),
        re.compile(r"require\s*\(\s*['\"](\S+)['\"]\s*\)"),
    ],
    "typescript": [
        re.compile(r"import\s+.*?\s+from\s+['\"](\S+)['\"]"),
        re.compile(r"import\s+['\"](\S+)['\"]"),
    ],
}

_DEFAULT_DEF_PATTERN = re.compile(r"(?:def\s+|class\s+|function\s+|fn\s+|func\s+)(\w+)")
_DEFAULT_IMPORT_PATTERN = re.compile(r"(?:import|require|from)\s+(\S+)")


def detect_language(file_path: str | Path) -> str:
    suffix = Path(file_path).suffix.lower()
    return _LANGUAGE_MAP.get(suffix, "text")


def is_binary(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _BINARY_EXTS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def skip_dir(dirname: str) -> bool:
    return dirname in _SKIP_DIRS


def extract_symbols(text: str, language: str) -> list[str]:
    symbols: list[str] = []
    patterns = _DEFINITION_PATTERNS.get(language, [_DEFAULT_DEF_PATTERN])
    for line in text.splitlines():
        for pat in patterns:
            m = pat.search(line)
            if m:
                symbols.append(m.group(1))
    return symbols


def extract_imports(text: str, language: str) -> list[str]:
    imports: list[str] = []
    patterns = _IMPORT_PATTERNS.get(language, [_DEFAULT_IMPORT_PATTERN])
    for line in text.splitlines():
        for pat in patterns:
            m = pat.search(line)
            if m:
                imports.append(m.group(1))
    return list(dict.fromkeys(imports))


def chunk_file(
    file_path: Path,
    workspace_root: Path,
    max_lines: int = DEFAULT_MAX_LINES,
    overlap: int = DEFAULT_OVERLAP,
) -> list[DocumentChunk]:
    if not file_path.is_file():
        return []
    if file_path.stat().st_size > MAX_FILE_BYTES:
        return []
    if is_binary(file_path):
        return []

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    if not text.strip():
        return []

    lang = detect_language(file_path)
    try:
        rel = str(file_path.relative_to(workspace_root))
    except ValueError:
        rel = file_path.name

    file_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    chunks: list[DocumentChunk] = []
    start = 0
    while start < total_lines:
        end = min(start + max_lines, total_lines)
        chunk_text = "".join(lines[start:end])

        chunk_id = str(uuid.uuid4().hex[:16])

        symbols = extract_symbols(chunk_text, lang)
        imports = extract_imports(chunk_text, lang)

        chunks.append(DocumentChunk(
            file_path=rel,
            language=lang,
            start_line=start + 1,
            end_line=end,
            text=chunk_text,
            chunk_id=chunk_id,
            symbols=symbols,
            imports=imports,
            file_hash=file_hash,
        ))

        if end >= total_lines:
            break
        start = end - overlap
        if start >= total_lines:
            break

    return chunks
