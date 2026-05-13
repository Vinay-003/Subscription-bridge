from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from subscription_bridge.core.errors import ParserError

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|[/\\])\.env(?:\.\w+)?$"),
    re.compile(r"(?:^|[/\\])\.ssh[/\\]"),
    re.compile(r"(?:^|[/\\])id_rsa$"),
    re.compile(r"(?:^|[/\\])id_ed25519$"),
    re.compile(r"(?:^|[/\\])known_hosts$"),
    re.compile(r"(?:^|[/\\])\.git[/\\]"),
    re.compile(r"(?:^|[/\\])cookies\."),
    re.compile(r"(?:^|[/\\])\.mypy_cache[/\\]"),
    re.compile(r"(?:^|[/\\])__pycache__[/\\]"),
]

_ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}

_HIDDEN_PREFIX = "."


@dataclass
class AttachmentInfo:
    path: str = ""
    filename: str = ""
    extension: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    category: str = "unknown"
    resolved_path: str = ""
    is_sensitive: bool = False
    is_archive: bool = False
    is_hidden: bool = False


@dataclass
class UploadConfig:
    enabled: bool = True
    max_files: int = 10
    max_file_bytes: int = 25_000_000
    upload_timeout_seconds: int = 180
    allow_unknown_extensions: bool = True
    block_archives: bool = False
    block_empty_files: bool = False
    block_hidden_files: bool = False
    block_sensitive_files: bool = True
    allow_paths_outside_workspace: bool = True


def load_upload_config(app_config: dict[str, Any] | None = None) -> UploadConfig:
    if app_config is None:
        from subscription_bridge.utils.config import load_config
        app_config = load_config()
    gemini_cfg = app_config.get("gemini", {})
    upload_cfg = gemini_cfg.get("uploads", {})
    return UploadConfig(
        enabled=bool(upload_cfg.get("enabled", True)),
        max_files=int(upload_cfg.get("max_files", 10)),
        max_file_bytes=int(upload_cfg.get("max_file_bytes", 25_000_000)),
        upload_timeout_seconds=int(upload_cfg.get("upload_timeout_seconds", 180)),
        allow_unknown_extensions=bool(upload_cfg.get("allow_unknown_extensions", True)),
        block_archives=bool(upload_cfg.get("block_archives", False)),
        block_empty_files=bool(upload_cfg.get("block_empty_files", False)),
        block_hidden_files=bool(upload_cfg.get("block_hidden_files", False)),
        block_sensitive_files=bool(upload_cfg.get("block_sensitive_files", True)),
        allow_paths_outside_workspace=bool(upload_cfg.get("allow_paths_outside_workspace", True)),
    )


def detect_extension(path: str | Path) -> str:
    p = Path(path)
    if p.suffix:
        return p.suffix.lower()
    name = p.name
    if "." in name:
        return name[name.rindex(".") :].lower()
    return ""


def classify_attachment(path: str | Path) -> AttachmentInfo:
    p = Path(path).expanduser().resolve()
    ext = detect_extension(p)
    mime_type, _ = mimetypes.guess_type(str(p))
    mime_type = mime_type or "application/octet-stream"

    category = _classify_extension(ext, mime_type)
    is_archive = ext in _ARCHIVE_EXTS
    is_hidden = p.name.startswith(_HIDDEN_PREFIX)
    is_sensitive = any(pat.search(str(p)) for pat in _SENSITIVE_PATTERNS)

    return AttachmentInfo(
        path=str(p),
        filename=p.name,
        extension=ext,
        mime_type=mime_type,
        size_bytes=0,
        category=category,
        resolved_path=str(p),
        is_sensitive=is_sensitive,
        is_archive=is_archive,
        is_hidden=is_hidden,
    )


def validate_attachment_path(
    path: str | Path,
    config: UploadConfig | None = None,
    workspace: str | None = None,
) -> AttachmentInfo:
    if config is None:
        config = load_upload_config()

    p = Path(path).expanduser()
    if not p.exists():
        msg = f"File not found: {path}"
        raise ParserError(str(path), msg)

    if p.is_dir():
        msg = f"Path is a directory, not a file: {path}"
        raise ParserError(str(path), msg)

    info = classify_attachment(p)
    stat = p.stat()
    info.size_bytes = stat.st_size

    if info.size_bytes > config.max_file_bytes:
        msg = (
            f"File too large: {path} ({info.size_bytes} bytes > "
            f"{config.max_file_bytes} max)"
        )
        raise ParserError(str(path), msg)

    if config.block_empty_files and info.size_bytes == 0:
        msg = f"Empty file blocked by policy: {path}"
        raise ParserError(str(path), msg)

    if config.block_hidden_files and info.is_hidden:
        msg = f"Hidden file blocked by policy: {path}"
        raise ParserError(str(path), msg)

    if config.block_sensitive_files and info.is_sensitive:
        msg = f"Sensitive file blocked by policy: {path}"
        raise ParserError(str(path), msg)

    if config.block_archives and info.is_archive:
        msg = f"Archive file blocked by policy: {path}"
        raise ParserError(str(path), msg)

    if not config.allow_paths_outside_workspace and workspace:
        ws = Path(workspace).expanduser().resolve()
        try:
            info.resolved_path = str(p.resolve())
            str(p.resolve()).startswith(str(ws))
        except (OSError, RuntimeError):
            msg = f"Symlink resolution failed: {path}"
            raise ParserError(str(path), msg)

    return info


def validate_attachments(
    paths: list[str],
    config: UploadConfig | None = None,
    workspace: str | None = None,
) -> list[AttachmentInfo]:
    if config is None:
        config = load_upload_config()

    if len(paths) > config.max_files:
        msg = f"Too many files: {len(paths)} (max {config.max_files})"
        raise ParserError("", msg)

    results: list[AttachmentInfo] = []
    for path in paths:
        info = validate_attachment_path(path, config, workspace)
        results.append(info)
    return results


def _classify_extension(ext: str, mime: str) -> str:
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
    document_exts = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf", ".txt", ".md", ".csv"}
    data_exts = {".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css"}
    code_exts = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".sh", ".bash", ".sql",
    }
    archive_exts = _ARCHIVE_EXTS

    if ext in image_exts:
        return "image"
    if ext in document_exts:
        return "document"
    if ext in data_exts:
        return "data"
    if ext in code_exts:
        return "code"
    if ext in archive_exts:
        return "archive"
    return "unknown"
