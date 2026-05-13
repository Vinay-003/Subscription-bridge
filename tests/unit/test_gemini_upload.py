from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.providers.gemini.attachments import AttachmentInfo, UploadConfig
from subscription_bridge.providers.gemini.upload import (
    UploadError,
    find_file_input,
    upload_files,
    visible_attachment_count,
    wait_for_uploads_to_settle,
)


class UploadLocator:
    def __init__(self, selector: str, visible: bool = True, count_val: int = 1) -> None:
        self._selector = selector
        self._visible = visible
        self._count_val = count_val
        self._clicked = False
        self._input_files: list[str] | None = None

    @property
    def first(self) -> UploadLocator:
        return self

    async def is_visible(self) -> bool:
        return self._visible

    async def count(self) -> int:
        return self._count_val

    async def click(self) -> None:
        self._clicked = True

    async def set_input_files(self, paths: list[str]) -> None:
        self._input_files = paths


class UploadPage:
    def __init__(self, input_visible: bool = True, input_count: int = 1) -> None:
        self._input_visible = input_visible
        self._input_count = input_count
        self._elements: list = []

    def locator(self, selector: str) -> UploadLocator:
        return UploadLocator(
            selector,
            visible=self._input_visible,
            count_val=self._input_count,
        )

    async def query_selector_all(self, selector: str) -> list:
        return self._elements


@pytest.mark.asyncio
async def test_find_file_input_found() -> None:
    page = UploadPage(input_visible=True, input_count=1)
    result = await find_file_input(page)
    assert result is not None


@pytest.mark.asyncio
async def test_find_file_input_not_found() -> None:
    page = UploadPage(input_visible=False, input_count=0)
    result = await find_file_input(page)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_uploads_settles_timeout() -> None:
    page = UploadPage()
    settled = await wait_for_uploads_to_settle(page, expected_count=2, timeout=1.0)
    assert settled is False


@pytest.mark.asyncio
async def test_visible_attachment_count_no_elements() -> None:
    page = UploadPage()
    count = await visible_attachment_count(page)
    assert count == 0


@pytest.mark.asyncio
async def test_upload_files_no_attachments() -> None:
    page = UploadPage()
    config = UploadConfig()
    result = await upload_files(page, [], config)
    assert result["success"] is True
    assert result["uploaded"] == 0


@pytest.mark.asyncio
async def test_upload_files_with_attachments(tmp_path: Path) -> None:
    page = UploadPage(input_visible=True, input_count=1)
    config = UploadConfig(upload_timeout_seconds=1)
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF")
    attachments = [
        AttachmentInfo(
            path=str(f),
            filename="test.pdf",
            extension=".pdf",
            resolved_path=str(f),
            category="document",
            size_bytes=4,
        )
    ]
    result = await upload_files(page, attachments, config)
    assert result["success"] is True
    assert result["uploaded"] == 1


@pytest.mark.asyncio
async def test_upload_files_no_file_input(tmp_path: Path) -> None:
    page = UploadPage(input_visible=False, input_count=0)
    config = UploadConfig(upload_timeout_seconds=1)
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF")
    attachments = [
        AttachmentInfo(
            path=str(f),
            filename="test.pdf",
            extension=".pdf",
            resolved_path=str(f),
            category="document",
        )
    ]
    with pytest.raises(UploadError, match="Could not find file input"):
        await upload_files(page, attachments, config)
