from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from subscription_bridge.browser.download_manager import DownloadError, DownloadManager


@pytest.fixture
def download_dir(tmp_path: Path) -> Path:
    d = tmp_path / "downloads"
    d.mkdir()
    return d


@pytest.fixture
def manager(download_dir: Path) -> DownloadManager:
    return DownloadManager(download_dir=download_dir, min_bytes=100)


def test_initialization(manager: DownloadManager) -> None:
    assert manager.download_dir.exists()


def test_download_dir_property(manager: DownloadManager, download_dir: Path) -> None:
    assert manager.download_dir == download_dir.resolve()


@pytest.mark.asyncio
async def test_wait_for_file_timeout(manager: DownloadManager) -> None:
    with pytest.raises(DownloadError, match="No valid download found"):
        await manager.wait_for_file(filename_prefix="nonexistent", timeout=0.1, poll_interval=0.05)


@pytest.mark.asyncio
async def test_wait_for_file_found(manager: DownloadManager, download_dir: Path) -> None:
    target = download_dir / "output.png"
    target.write_bytes(b"x" * 200)
    time.sleep(0.1)

    result = await manager.wait_for_file(filename_prefix="output", timeout=5.0, poll_interval=0.05)
    assert result == target.resolve()


@pytest.mark.asyncio
async def test_wait_for_file_ignores_temp(manager: DownloadManager, download_dir: Path) -> None:
    temp_file = download_dir / "output.png.crdownload"
    temp_file.write_bytes(b"x" * 200)

    with pytest.raises(DownloadError, match="No valid download found"):
        await manager.wait_for_file(filename_prefix="output", timeout=0.1, poll_interval=0.05)


@pytest.mark.asyncio
async def test_wait_for_file_ignores_small(manager: DownloadManager, download_dir: Path) -> None:
    small_file = download_dir / "small.png"
    small_file.write_bytes(b"x" * 50)

    with pytest.raises(DownloadError, match="No valid download found"):
        await manager.wait_for_file(filename_prefix="small", timeout=0.1, poll_interval=0.05)


@pytest.mark.asyncio
async def test_wait_for_file_returns_on_timeout_with_large_file(manager: DownloadManager, download_dir: Path) -> None:
    valid = download_dir / "partial_result.png"
    valid.write_bytes(b"x" * 200)

    result = await manager.wait_for_file(filename_prefix="partial", timeout=0.1, poll_interval=0.05)
    assert result == valid.resolve()


def test_cleanup_old(manager: DownloadManager, download_dir: Path) -> None:
    old_file = download_dir / "old.txt"
    old_file.write_text("old data")
    old_time = time.time() - 48 * 3600
    os.utime(str(old_file), (old_time, old_time))


    removed = manager.cleanup_old(max_age_hours=24)
    assert removed == 1
    assert not old_file.exists()


def test_cleanup_old_keeps_recent(manager: DownloadManager, download_dir: Path) -> None:
    new_file = download_dir / "new.txt"
    new_file.write_text("new data")

    removed = manager.cleanup_old(max_age_hours=24)
    assert removed == 0
    assert new_file.exists()
