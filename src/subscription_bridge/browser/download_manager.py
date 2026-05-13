from __future__ import annotations

import time
from pathlib import Path
from typing import Any

DOWNLOAD_TEMP_EXTS = {".crdownload", ".tmp", ".part"}
_DEFAULT_MIN_BYTES = 20_000


class DownloadError(Exception):
    ...


class DownloadManager:
    def __init__(self, download_dir: str | Path, min_bytes: int = _DEFAULT_MIN_BYTES) -> None:
        self._download_dir = Path(download_dir).expanduser().resolve()
        self._min_bytes = min_bytes
        self._download_dir.mkdir(parents=True, exist_ok=True)

    async def wait_for_file(
        self,
        filename_prefix: str = "",
        timeout: float = 180.0,
        poll_interval: float = 1.0,
    ) -> Path:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = self._find_candidates(filename_prefix)
            valid = [p for p in candidates if self._is_valid_download(p)]
            if valid:
                return valid[0]
            await _sleep(poll_interval)

        candidates = [p for p in self._find_candidates(filename_prefix) if self._is_valid_download(p)]
        if candidates:
            largest = max(candidates, key=lambda p: p.stat().st_size)
            if largest.stat().st_size > 0:
                return largest

        msg = f"No valid download found in {self._download_dir} (prefix={filename_prefix!r}, timeout={timeout}s)"
        raise DownloadError(msg)

    def _find_candidates(self, prefix: str) -> list[Path]:
        if not self._download_dir.exists():
            return []
        if prefix:
            return sorted(self._download_dir.glob(f"{prefix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return sorted(self._download_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

    def _is_valid_download(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix.lower() in DOWNLOAD_TEMP_EXTS:
            return False
        try:
            if path.stat().st_size < self._min_bytes:
                return False
        except OSError:
            return False
        return True

    @property
    def download_dir(self) -> Path:
        return self._download_dir

    def cleanup_old(self, max_age_hours: float = 24.0) -> int:
        if not self._download_dir.exists():
            return 0
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        for path in self._download_dir.iterdir():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed


async def expect_download(page: Any, timeout: float = 180.0) -> Any:
    try:
        async with page.expect_download(timeout=timeout * 1000) as download_info:
            return await download_info.value
    except Exception:
        return None


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
