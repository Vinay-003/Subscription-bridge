from __future__ import annotations

import asyncio

import pytest

from subscription_bridge.utils.async_utils import (
    OperationTimeoutError,
    gather_with_concurrency,
    run_sync_with_timeout,
    run_with_timeout,
)


@pytest.mark.asyncio
async def test_run_with_timeout_success() -> None:
    async def work() -> str:
        await asyncio.sleep(0.01)
        return "done"

    result = await run_with_timeout(work(), timeout_seconds=5.0)
    assert result == "done"


@pytest.mark.asyncio
async def test_run_with_timeout_expires() -> None:
    async def slow() -> str:
        await asyncio.sleep(10.0)
        return "never"

    with pytest.raises(OperationTimeoutError) as excinfo:
        await run_with_timeout(slow(), timeout_seconds=0.01)

    assert excinfo.value.timeout_seconds == 0.01


@pytest.mark.asyncio
async def test_run_with_timeout_custom_message() -> None:
    async def slow() -> str:
        await asyncio.sleep(10.0)
        return "never"

    with pytest.raises(OperationTimeoutError) as excinfo:
        await run_with_timeout(slow(), timeout_seconds=0.01, timeout_message="custom msg")

    assert "custom msg" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_sync_with_timeout_success() -> None:
    def work() -> str:
        return "sync done"

    result = await run_sync_with_timeout(work, timeout_seconds=5.0)
    assert result == "sync done"


@pytest.mark.asyncio
async def test_run_sync_with_timeout_expires() -> None:
    def slow() -> None:
        import time

        time.sleep(10.0)

    with pytest.raises(OperationTimeoutError):
        await run_sync_with_timeout(slow, timeout_seconds=0.01)


@pytest.mark.asyncio
async def test_gather_with_concurrency() -> None:
    results: list[int] = []

    async def work(n: int) -> int:
        results.append(n)
        await asyncio.sleep(0.01)
        return n * 2

    output = await gather_with_concurrency(2, *(work(i) for i in range(5)))
    assert output == [0, 2, 4, 6, 8]


@pytest.mark.asyncio
async def test_gather_with_concurrency_respects_limit() -> None:
    semaphore_count = 0
    max_concurrent = 0

    async def work(n: int) -> int:
        nonlocal semaphore_count, max_concurrent
        semaphore_count += 1
        max_concurrent = max(max_concurrent, semaphore_count)
        await asyncio.sleep(0.05)
        semaphore_count -= 1
        return n

    await gather_with_concurrency(3, *(work(i) for i in range(6)))
    assert max_concurrent <= 3


@pytest.mark.asyncio
async def test_gather_with_concurrency_empty() -> None:
    output = await gather_with_concurrency(5)
    assert output == []


@pytest.mark.asyncio
async def test_gather_with_concurrency_return_exceptions() -> None:
    async def fail() -> str:
        raise ValueError("fail")

    async def ok() -> str:
        return "ok"

    results = await gather_with_concurrency(
        2,
        fail(),
        ok(),
        return_exceptions=True,
    )
    assert isinstance(results[0], ValueError)
    assert results[1] == "ok"


def test_operation_timeout_error_repr() -> None:
    error = OperationTimeoutError(5.0)
    assert error.timeout_seconds == 5.0
    assert "5.0" in str(error)
