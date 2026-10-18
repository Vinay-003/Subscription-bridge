from __future__ import annotations

import pytest

from subscription_bridge.providers.chatgpt.adapter import (
    _set_thinking,
    _variant_wants_thinking,
)


class FakeLocator:
    def __init__(self, pressed: bool | None, present: bool = True) -> None:
        self._pressed = pressed
        self._present = present
        self.clicks = 0

    async def count(self) -> int:
        return 1 if self._present else 0

    async def get_attribute(self, name: str) -> str | None:
        if name == "aria-pressed" and self._pressed is not None:
            return "true" if self._pressed else "false"
        return None

    async def click(self) -> None:
        self.clicks += 1
        if self._pressed is not None:
            self._pressed = not self._pressed


class FakeFirst:
    def __init__(self, loc: FakeLocator) -> None:
        self._loc = loc

    async def count(self) -> int:
        return await self._loc.count()

    async def get_attribute(self, name: str) -> str | None:
        return await self._loc.get_attribute(name)

    async def click(self) -> None:
        await self._loc.click()


class FakeLocatorChain:
    def __init__(self, loc: FakeLocator) -> None:
        self.first = FakeFirst(loc)


class FakePage:
    def __init__(self, loc: FakeLocator) -> None:
        self._loc = loc

    def locator(self, selector: str) -> FakeLocatorChain:
        return FakeLocatorChain(self._loc)


def test_variant_wants_thinking_for_known_variants() -> None:
    assert _variant_wants_thinking("Thinking") is True
    assert _variant_wants_thinking("Pro") is True
    assert _variant_wants_thinking("thinking") is True
    assert _variant_wants_thinking("Instant") is False
    assert _variant_wants_thinking("instant") is False
    assert _variant_wants_thinking("fast") is False
    assert _variant_wants_thinking("gpt-4o") is False
    assert _variant_wants_thinking("auto") is False


@pytest.mark.asyncio
async def test_set_thinking_skips_click_when_already_pressed() -> None:
    loc = FakeLocator(pressed=True)
    page = FakePage(loc)

    ok = await _set_thinking(page, "Thinking")

    assert ok is True
    assert loc.clicks == 0


@pytest.mark.asyncio
async def test_set_thinking_clicks_to_enable_thinking_variant() -> None:
    loc = FakeLocator(pressed=False)
    page = FakePage(loc)

    ok = await _set_thinking(page, "thinking")

    assert ok is True
    assert loc.clicks == 1
    assert loc._pressed is True


@pytest.mark.asyncio
async def test_set_thinking_clicks_to_disable_instant_variant() -> None:
    loc = FakeLocator(pressed=True)
    page = FakePage(loc)

    ok = await _set_thinking(page, "Instant")

    assert ok is True
    assert loc.clicks == 1
    assert loc._pressed is False


@pytest.mark.asyncio
async def test_set_thinking_returns_false_when_button_missing() -> None:
    loc = FakeLocator(pressed=None, present=False)
    page = FakePage(loc)

    ok = await _set_thinking(page, "Thinking")

    assert ok is False
    assert loc.clicks == 0


@pytest.mark.asyncio
async def test_set_thinking_unknown_variant_is_off_by_default() -> None:
    loc = FakeLocator(pressed=True)
    page = FakePage(loc)

    ok = await _set_thinking(page, "gpt-5")

    assert ok is True
    assert loc.clicks == 1
    assert loc._pressed is False


def test_composer_matches_exact_and_paste_chrome() -> None:
    from subscription_bridge.providers.chatgpt.adapter import _composer_matches

    short = "hello world"
    assert _composer_matches(short, short)
    assert _composer_matches(f"  {short}\n", short)
    assert _composer_matches(f"Pasted text\n{short}", short)
    assert _composer_matches(f"{short} Pasted text", short)
    assert not _composer_matches("stale composer content", short)
    assert not _composer_matches("hello", short)


def test_composer_matches_long_pasted_text_with_label_margin() -> None:
    from subscription_bridge.providers.chatgpt.adapter import _composer_matches

    long_text = ("Pasted paragraphs of prompt text that keep going. " * 20).strip()
    assert len(long_text) >= 200
    assert _composer_matches(long_text, long_text)
    assert _composer_matches(f"Pasted text\n{long_text}", long_text)
    assert _composer_matches(f"{long_text}\nPasted text", long_text)
    # Partial insert of only the beginning must not pass.
    assert not _composer_matches(long_text[:120], long_text)
    # Unrelated content must not pass.
    assert not _composer_matches(long_text.replace("prompt", "different"), long_text)
