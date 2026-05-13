from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


class OperationTimeoutError(Exception):
    def __init__(self, timeout_seconds: float, message: str = "") -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(message or f"Operation timed out after {timeout_seconds}s")


async def run_with_timeout(
    awaitable: Awaitable[T],
    timeout_seconds: float,
    timeout_message: str = "",
) -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as e:
        raise OperationTimeoutError(timeout_seconds, timeout_message) from e


async def run_sync_with_timeout(
    func: Callable[..., T],
    timeout_seconds: float,
    *args: Any,
    timeout_message: str = "",
    **kwargs: Any,
) -> T:
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: func(*args, **kwargs)),
            timeout=timeout_seconds,
        )
    except TimeoutError as e:
        raise OperationTimeoutError(timeout_seconds, timeout_message) from e


async def gather_with_concurrency(
    limit: int,
    *tasks: Awaitable[T],
    return_exceptions: bool = False,
) -> list[T]:
    semaphore = asyncio.Semaphore(limit)

    async def _run(task: Awaitable[T]) -> T:
        async with semaphore:
            return await task

    results = await asyncio.gather(
        *(_run(t) for t in tasks), return_exceptions=return_exceptions
    )
    return cast(list[T], list(results))
