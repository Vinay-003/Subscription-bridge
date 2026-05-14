from __future__ import annotations

from pathlib import Path

import pytest

from subscription_bridge.providers.gemini.attachments import AttachmentInfo, UploadConfig
from subscription_bridge.providers.gemini.upload import (
    UploadError,
    upload_files,
)
from subscription_bridge.providers.gemini.upload import (
    _visible_uploaded_image_count as visible_attachment_count,
)
from subscription_bridge.providers.gemini.upload import (
    _wait_for_uploads_settle as wait_for_uploads_to_settle,
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


class CdpSession:
    def __init__(self) -> None:
        self._doc_id: str | None = None

    async def send(self, method: str, params: dict | None = None) -> dict:
        if method == "DOM.getDocument":
            self._doc_id = "root-1"
            return {"root": {"nodeId": 1}}
        if method == "DOM.querySelectorAll":
            return {"nodeIds": [2]}
        if method == "DOM.describeNode":
            return {"node": {"attributes": []}}
        if method == "DOM.setFileInputFiles":
            return {}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "obj-1"}}
        if method == "Runtime.callFunctionOn":
            return {}
        return {}


class UploadPage:
    def __init__(self, input_visible: bool = True, input_count: int = 1) -> None:
        self._input_visible = input_visible
        self._input_count = input_count
        self._elements: list = []
        self._context_obj = self

    def locator(self, selector: str) -> UploadLocator:
        return UploadLocator(
            selector,
            visible=self._input_visible,
            count_val=self._input_count,
        )

    async def query_selector_all(self, selector: str) -> list:
        return self._elements

    def new_cdp_session(self, page: object) -> CdpSession:
        return CdpSession()

    async def evaluate(self, script: str, *args: object) -> object:
        return None

    @property
    def context(self) -> UploadPage:
        return self


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
    assert result["method"] == "none"


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
async def test_upload_binary_file_fallsback_to_text_inline_fails(tmp_path: Path) -> None:
    page = UploadPage(input_visible=False, input_count=0)
    config = UploadConfig(upload_timeout_seconds=1)
    f = tmp_path / "test.bin"
    f.write_bytes(b"\xff\xfe\x00\x01\x00\x02\x00\x03")
    attachments = [
        AttachmentInfo(
            path=str(f),
            filename="test.bin",
            extension=".bin",
            resolved_path=str(f),
            category="unknown",
        )
    ]
    with pytest.raises(UploadError, match="not a readable text file"):
        await upload_files(page, attachments, config)


@pytest.mark.asyncio
async def test_upload_text_file_fallsback_to_text_inline(tmp_path: Path) -> None:
    page = UploadPage(input_visible=False, input_count=0)
    config = UploadConfig(upload_timeout_seconds=1)
    f = tmp_path / "test.py"
    f.write_text("print('hello')")
    attachments = [
        AttachmentInfo(
            path=str(f),
            filename="test.py",
            extension=".py",
            resolved_path=str(f),
            category="code",
            size_bytes=14,
        )
    ]
    result = await upload_files(page, attachments, config)
    assert result["success"] is True
    assert result["uploaded"] == 1
    assert result["method"] == "text_inline"
    assert len(result["text_contents"]) == 1
    assert result["text_contents"][0]["content"] == "print('hello')"
