from __future__ import annotations

import asyncio

_workspace_locks: dict[str, asyncio.Lock] = {}
_workspace_locks_guard = asyncio.Lock()


async def get_workspace_lock(workspace: str) -> asyncio.Lock:
    async with _workspace_locks_guard:
        lock = _workspace_locks.get(workspace)
        if lock is None:
            lock = asyncio.Lock()
            _workspace_locks[workspace] = lock
        return lock
