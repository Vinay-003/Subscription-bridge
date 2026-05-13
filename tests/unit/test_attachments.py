from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.core.errors import ParserError
from subscription_bridge.providers.gemini.attachments import (
    AttachmentInfo,
    UploadConfig,
    classify_attachment,
    detect_extension,
    validate_attachment_path,
    validate_attachments,
)


def test_detect_extension_known() -> None:
    assert detect_extension("file.pdf") == ".pdf"
    assert detect_extension("file.PNG") == ".png"
    assert detect_extension("file.tar.gz") == ".gz"


def test_detect_extension_none() -> None:
    assert detect_extension("makefile") == ""
    assert detect_extension("README") == ""


def test_classify_image() -> None:
    info = classify_attachment("photo.png")
    assert info.category == "image"


def test_classify_document() -> None:
    info = classify_attachment("report.pdf")
    assert info.category == "document"


def test_classify_code() -> None:
    info = classify_attachment("script.py")
    assert info.category == "code"


def test_classify_unknown() -> None:
    info = classify_attachment("data.customext")
    assert info.category == "unknown"


def test_classify_archive() -> None:
    info = classify_attachment("archive.zip")
    assert info.is_archive is True
    assert info.category == "archive"


def test_validate_normal_pdf(tmp_path: Path) -> None:
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4 fake pdf content")
    info = validate_attachment_path(str(f))
    assert info.filename == "test.pdf"
    assert info.category == "document"


def test_validate_normal_png(tmp_path: Path) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"fake png")
    info = validate_attachment_path(str(f))
    assert info.category == "image"


def test_validate_py_file(tmp_path: Path) -> None:
    f = tmp_path / "script.py"
    f.write_text("print('hello')")
    info = validate_attachment_path(str(f))
    assert info.category == "code"


def test_validate_unknown_ext_allowed(tmp_path: Path) -> None:
    f = tmp_path / "data.customext"
    f.write_text("some custom format data")
    info = validate_attachment_path(str(f))
    assert info.category == "unknown"


def test_validate_extensionless_allowed(tmp_path: Path) -> None:
    f = tmp_path / "Makefile"
    f.write_text("all:\n\techo hello")
    info = validate_attachment_path(str(f))
    assert info.extension == ""


def test_validate_missing_file() -> None:
    with pytest.raises(ParserError, match="not found"):
        validate_attachment_path("/nonexistent/file.pdf")


def test_validate_directory(tmp_path: Path) -> None:
    with pytest.raises(ParserError, match="directory"):
        validate_attachment_path(str(tmp_path))


def test_validate_oversized(tmp_path: Path) -> None:
    f = tmp_path / "huge.bin"
    f.write_bytes(b"x" * 30_000_000)
    with pytest.raises(ParserError, match="too large"):
        validate_attachment_path(str(f))


def test_validate_oversized_with_config(tmp_path: Path) -> None:
    f = tmp_path / "medium.bin"
    f.write_bytes(b"x" * 1000)
    config = UploadConfig(max_file_bytes=500)
    with pytest.raises(ParserError, match="too large"):
        validate_attachment_path(str(f), config)


def test_validate_sensitive_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("SECRET=value")
    with pytest.raises(ParserError, match="blocked by policy"):
        validate_attachment_path(str(f))


def test_validate_sensitive_allowed_when_disabled(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("SECRET=value")
    config = UploadConfig(block_sensitive_files=False)
    info = validate_attachment_path(str(f), config)
    assert info.filename == ".env"


def test_validate_archive_blocked(tmp_path: Path) -> None:
    f = tmp_path / "data.zip"
    f.write_bytes(b"PK")
    config = UploadConfig(block_archives=True)
    with pytest.raises(ParserError, match="blocked by policy"):
        validate_attachment_path(str(f), config)


def test_validate_archive_allowed_by_default(tmp_path: Path) -> None:
    f = tmp_path / "data.zip"
    f.write_bytes(b"PK")
    info = validate_attachment_path(str(f))
    assert info.is_archive is True


def test_validate_hidden_file_blocked(tmp_path: Path) -> None:
    f = tmp_path / ".hidden_file"
    f.write_text("secret")
    config = UploadConfig(block_hidden_files=True)
    with pytest.raises(ParserError, match="blocked by policy"):
        validate_attachment_path(str(f), config)


def test_validate_hidden_file_allowed(tmp_path: Path) -> None:
    f = tmp_path / ".hidden_file"
    f.write_text("secret")
    info = validate_attachment_path(str(f))
    assert info.is_hidden is True


def test_validate_empty_file_blocked(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("")
    config = UploadConfig(block_empty_files=True)
    with pytest.raises(ParserError, match="blocked by policy"):
        validate_attachment_path(str(f), config)


def test_validate_too_many_files(tmp_path: Path) -> None:
    paths: list[str] = []
    for i in range(15):
        f = tmp_path / f"file{i}.txt"
        f.write_text("content")
        paths.append(str(f))
    with pytest.raises(ParserError, match="Too many"):
        validate_attachments(paths)


def test_validate_multiple_good(tmp_path: Path) -> None:
    for name in ["a.pdf", "b.png", "c.py"]:
        (tmp_path / name).write_text("content")
    infos = validate_attachments(
        [str(tmp_path / "a.pdf"), str(tmp_path / "b.png"), str(tmp_path / "c.py")]
    )
    assert len(infos) == 3


def test_attachment_info_fields(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    info = validate_attachment_path(str(f))
    assert isinstance(info, AttachmentInfo)
    assert info.filename == "test.py"
    assert info.extension == ".py"
    assert info.size_bytes > 0
    assert info.resolved_path
    assert info.mime_type
