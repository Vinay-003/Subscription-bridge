from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


class RetryConfig:
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff: float = 2.0,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff = backoff
        self.retryable_exceptions = retryable_exceptions


DEFAULT_RETRY = RetryConfig()
BROWSER_RETRY = RetryConfig(max_attempts=5, base_delay=2.0, backoff=2.0)
PROVIDER_RETRY = RetryConfig(max_attempts=3, base_delay=1.0, backoff=2.0)


def retry(
    config: RetryConfig = DEFAULT_RETRY,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper_sync(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exc = e
                    if attempt + 1 < config.max_attempts:
                        delay = min(config.base_delay * (config.backoff**attempt), config.max_delay)
                        import time

                        time.sleep(delay)
            msg = f"All {config.max_attempts} attempts failed"
            raise RetryError(msg) from last_exc

        @functools.wraps(func)
        async def wrapper_async(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            async_func = cast(Callable[P, Awaitable[R]], func)
            for attempt in range(config.max_attempts):
                try:
                    return await async_func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exc = e
                    if attempt + 1 < config.max_attempts:
                        delay = min(config.base_delay * (config.backoff**attempt), config.max_delay)
                        await asyncio.sleep(delay)
            msg = f"All {config.max_attempts} attempts failed"
            raise RetryError(msg) from last_exc

        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], wrapper_async)
        return cast(Callable[P, R], wrapper_sync)

    return decorator


async def retry_async(
    func: Callable[..., Awaitable[R]],
    *args: Any,
    config: RetryConfig = DEFAULT_RETRY,
    **kwargs: Any,
) -> R:
    last_exc: Exception | None = None
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exc = e
            if attempt + 1 < config.max_attempts:
                delay = min(config.base_delay * (config.backoff**attempt), config.max_delay)
                await asyncio.sleep(delay)
    msg = f"All {config.max_attempts} attempts failed"
    raise RetryError(msg) from last_exc


class RetryError(Exception):
    def __init__(self, message: str = "") -> None:
        super().__init__(message)
