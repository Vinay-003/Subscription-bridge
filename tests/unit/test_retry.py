from __future__ import annotations

import pytest

from subscription_bridge.utils.retry import (
    BROWSER_RETRY,
    PROVIDER_RETRY,
    RetryConfig,
    RetryError,
    retry,
    retry_async,
)


def test_retry_config_defaults() -> None:
    config = RetryConfig()
    assert config.max_attempts == 3
    assert config.base_delay == 1.0
    assert config.max_delay == 30.0
    assert config.backoff == 2.0


def test_retry_config_custom() -> None:
    config = RetryConfig(max_attempts=5, base_delay=2.0, backoff=3.0)
    assert config.max_attempts == 5
    assert config.base_delay == 2.0
    assert config.backoff == 3.0


def test_browser_retry_defaults() -> None:
    assert BROWSER_RETRY.max_attempts == 5
    assert BROWSER_RETRY.base_delay == 2.0


def test_provider_retry_defaults() -> None:
    assert PROVIDER_RETRY.max_attempts == 3
    assert PROVIDER_RETRY.base_delay == 1.0


def test_retry_sync_success() -> None:
    call_count = 0

    @retry()
    def do_work() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = do_work()
    assert result == "ok"
    assert call_count == 1


def test_retry_sync_eventual_success() -> None:
    call_count = 0

    @retry(config=RetryConfig(max_attempts=3, base_delay=0.01))
    def do_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    result = do_work()
    assert result == "ok"
    assert call_count == 3


def test_retry_sync_exhausted() -> None:
    call_count = 0

    @retry(config=RetryConfig(max_attempts=2, base_delay=0.01))
    def do_work() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("always fails")

    with pytest.raises(RetryError) as excinfo:
        do_work()
    assert call_count == 2
    assert "All 2 attempts failed" in str(excinfo.value)


@pytest.mark.asyncio
async def test_retry_async_success() -> None:
    call_count = 0

    @retry()
    async def do_work() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await do_work()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_eventual_success() -> None:
    call_count = 0

    @retry(config=RetryConfig(max_attempts=3, base_delay=0.01))
    async def do_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    result = await do_work()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausted() -> None:
    call_count = 0

    @retry(config=RetryConfig(max_attempts=2, base_delay=0.01))
    async def do_work() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("always fails")

    with pytest.raises(RetryError):
        await do_work()
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_async_helper() -> None:
    call_count = 0

    async def do_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("not yet")
        return "ok"

    result = await retry_async(
        do_work,
        config=RetryConfig(max_attempts=3, base_delay=0.01),
    )
    assert result == "ok"
    assert call_count == 2


def test_retry_base_exception_passthrough() -> None:
    @retry()
    def do_work() -> str:
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        do_work()


def test_retry_custom_exception_types() -> None:
    call_count = 0

    @retry(config=RetryConfig(max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,)))
    def do_work() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("retryable")
        raise TypeError("non-retryable")

    with pytest.raises(TypeError):
        do_work()
    assert call_count == 2
