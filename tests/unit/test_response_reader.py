from __future__ import annotations

from typing import Any

from subscription_bridge.providers.gemini.response_reader import extract_latest_assistant_text


class FakePage:
    def __init__(self) -> None:
        self._elements: dict[str, list[dict[str, str]]] = {}
        self._query_results: list[dict] | None = None

    def set_elements(self, selector: str, elements: list[dict[str, str]]) -> None:
        self._elements[selector] = elements

    async def query_selector_all(self, selector: str) -> list:
        elements = self._elements.get(selector, [])
        return [FakeElement(e) for e in elements]

    async def evaluate(self, script: str, *args: Any) -> str | list:
        return ""


class FakeElement:
    def __init__(self, data: dict[str, str]) -> None:
        self._data = data
        self._visible = data.get("visible", "true") == "true"

    async def is_visible(self) -> bool:
        return self._visible

    async def inner_text(self) -> str:
        return self._data.get("text", "")

    async def get_attribute(self, name: str) -> str | None:
        return self._data.get(name)


async def test_extract_empty_when_no_response() -> None:
    class EmptyPage:
        async def evaluate(self, script: str, *args: Any) -> str:
            return ""

    result = await extract_latest_assistant_text(EmptyPage())
    assert result == ""


async def test_extract_empty_when_evaluate_fails() -> None:
    class FailingPage:
        async def evaluate(self, script: str, *args: Any) -> str:
            raise RuntimeError("fail")

    result = await extract_latest_assistant_text(FailingPage())
    assert result == ""
