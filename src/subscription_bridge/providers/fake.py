from __future__ import annotations

import time
import uuid

from subscription_bridge.providers.base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderRequest,
    ProviderResponse,
)


class FakeProviderAdapter(ProviderAdapter):
    name = "fake"
    capabilities: set[ProviderCapability] = {"text_chat", "code_reasoning"}

    def __init__(
        self,
        fail_rate: float = 0.0,
        response_delay: float = 0.0,
        scripted_responses: list[str] | None = None,
    ) -> None:
        self._fail_rate = fail_rate
        self._response_delay = response_delay
        self._scripted = scripted_responses or []
        self._script_index = 0
        self._sessions: set[str] = set()

    async def create_session(self) -> str:
        session_id = f"fake-{uuid.uuid4().hex[:12]}"
        self._sessions.add(session_id)
        return session_id

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        import random

        start = time.monotonic()

        if self._response_delay > 0:
            await self._simulate_delay()

        if random.random() < self._fail_rate:
            return ProviderResponse(
                provider=self.name,
                text="",
                raw_text="",
                success=False,
                latency_seconds=time.monotonic() - start,
                error="Simulated provider failure",
            )

        if self._scripted:
            if self._script_index < len(self._scripted):
                text = self._scripted[self._script_index]
                self._script_index += 1
            else:
                text = self._scripted[-1]

            return ProviderResponse(
                provider=self.name,
                text=text,
                raw_text=text,
                success=True,
                latency_seconds=time.monotonic() - start,
            )

        if request.require_json:
            text = self._generate_json_response(request.prompt)
        else:
            text = self._generate_text_response(request.prompt)

        return ProviderResponse(
            provider=self.name,
            text=text,
            raw_text=text,
            success=True,
            latency_seconds=time.monotonic() - start,
        )

    async def reset_chat(self, session_id: str) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def close_session(self, session_id: str) -> None:
        self._sessions.discard(session_id)

    def reset_script(self) -> None:
        self._script_index = 0

    async def _simulate_delay(self) -> None:
        import asyncio

        await asyncio.sleep(self._response_delay)

    def _generate_text_response(self, prompt: str) -> str:
        prompt_lower = prompt.lower()

        if "hello" in prompt_lower or "hi" in prompt_lower:
            return "Hello! I am SubscriptionBridge's fake provider. I'm ready to help you test the agent runtime."

        if "json" in prompt_lower:
            return self._generate_json_response(prompt)

        if "error" in prompt_lower or "fail" in prompt_lower:
            return (
                '{"type": "final", "thought": "Simulating an error response", '
                '"answer": "An error occurred while processing your request."}'
            )

        return (
            '{"type": "final", "thought": "Processed your request successfully", '
            '"answer": "This is a deterministic response from the fake provider. '
            'The agent runtime is working correctly. Your prompt was: '
            + prompt[:100].replace('"', "'")
            + '"}'
        )

    def _generate_json_response(self, prompt: str) -> str:
        import json

        return json.dumps(
            {
                "type": "final",
                "thought": "Generated JSON response for testing",
                "answer": f"Received prompt: {prompt[:100]}",
            }
        )

    @property
    def active_sessions(self) -> list[str]:
        return list(self._sessions)
