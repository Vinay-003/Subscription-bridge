from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


def run_async(coro: Awaitable[T], timeout: float | None = None) -> T:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[T] = []
    exc: list[BaseException] = []

    def _run() -> None:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            result.append(
                new_loop.run_until_complete(
                    asyncio.wait_for(coro, timeout) if timeout else coro
                )
            )
        except BaseException as e:
            exc.append(e)
        finally:
            new_loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()
    if exc:
        raise exc[0]
    return result[0]


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
