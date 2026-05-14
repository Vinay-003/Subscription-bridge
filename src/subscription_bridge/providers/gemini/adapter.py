from __future__ import annotations

import time
from typing import Any

from subscription_bridge.browser.session_pool import SessionPool
from subscription_bridge.browser.tab_session import TabSession
from subscription_bridge.providers.base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderRequest,
    ProviderResponse,
)
from subscription_bridge.providers.gemini.attachments import (
    load_upload_config,
    validate_attachments,
)
from subscription_bridge.providers.gemini.health import (
    check_gemini_ready,
    check_provider_health,
    navigate_to_fresh_chat,
)
from subscription_bridge.providers.gemini.prompt_io import (
    find_composer,
    set_prompt_text,
)
from subscription_bridge.providers.gemini.response_reader import (
    extract_latest_assistant_text,
    wait_for_response_complete,
    wait_for_send_confirmation,
)
from subscription_bridge.providers.gemini.upload import UploadError, upload_files


class GeminiError(Exception):
    ...


class GeminiProviderAdapter(ProviderAdapter):
    name = "gemini"
    capabilities: set[ProviderCapability] = {"text_chat", "code_reasoning", "file_upload", "vision"}

    def __init__(self, session_pool: SessionPool, page_factory: Any) -> None:
        self._pool = session_pool
        self._page_factory = page_factory

    async def create_session(self) -> str:
        session = await self._pool.acquire("gemini", "", self._page_factory)
        return session.session_id

    async def send_prompt(self, request: ProviderRequest) -> ProviderResponse:
        start = time.monotonic()
        session: TabSession | None = None
        upload_meta: dict[str, Any] | None = None
        prompt = request.prompt

        try:
            session = await self._pool.acquire("gemini", request.run_id, self._page_factory)
            await self._ensure_fresh_chat(session)

            if request.attachments:
                upload_meta = await self._handle_attachments(session, request.attachments, start)
                if upload_meta.get("upload_method") == "text_inline":
                    preamble_parts = []
                    for i, fname in enumerate(upload_meta.get("inline_text_attachments", [])):
                        content = upload_meta.get("inline_text_contents", [{}])[i].get("content", "")
                        if content:
                            preamble_parts.append(f"[File: {fname}]\n```\n{content}\n```")
                    if preamble_parts:
                        prompt = "\n\n".join(preamble_parts) + "\n\n" + prompt

            if request.require_json and not any(marker in prompt for marker in ["STRICT JSON", "Return STRICT JSON"]):
                prompt += "\n\nYou MUST return STRICT JSON only. No Markdown. No prose outside JSON."

            await find_composer(session.page)
            await set_prompt_text(session.page, prompt)

            from subscription_bridge.providers.gemini.prompt_io import submit_via_enter
            await submit_via_enter(session.page)

            accepted = await wait_for_send_confirmation(session.page, timeout=35.0)
            if not accepted:
                await session.screenshot_debug("send_not_confirmed")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini did not confirm prompt submission",
                    metadata=upload_meta or {},
                )

            complete = await wait_for_response_complete(session.page, timeout=120.0)
            if not complete:
                await session.screenshot_debug("response_timeout")
                text = await extract_latest_assistant_text(session.page)
                if text:
                    return ProviderResponse(
                        provider=self.name, text=text, raw_text=text, success=True,
                        latency_seconds=time.monotonic() - start,
                        metadata=upload_meta or {},
                    )
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini did not produce a response within timeout",
                    metadata=upload_meta or {},
                )

            text = await extract_latest_assistant_text(session.page)
            if not text:
                await session.screenshot_debug("empty_response")
                return ProviderResponse(
                    provider=self.name, text="", raw_text="", success=False,
                    latency_seconds=time.monotonic() - start,
                    error="Gemini returned empty response",
                    metadata=upload_meta or {},
                )

            return ProviderResponse(
                provider=self.name, text=text, raw_text=text, success=True,
                latency_seconds=time.monotonic() - start,
                metadata=upload_meta or {},
            )

        except (UploadError, ValueError) as e:
            if session is not None:
                await session.screenshot_debug("upload_error")
            return ProviderResponse(
                provider=self.name, text="", raw_text="", success=False,
                latency_seconds=time.monotonic() - start,
                error=str(e), metadata=upload_meta or {},
            )
        except Exception as e:
            if session is not None:
                await session.screenshot_debug("provider_error")
            return ProviderResponse(
                provider=self.name, text="", raw_text="", success=False,
                latency_seconds=time.monotonic() - start,
                error=f"Gemini provider error: {e}", metadata=upload_meta or {},
            )
        finally:
            if session is not None:
                await self._pool.release(session.session_id)

    async def _handle_attachments(
        self,
        session: TabSession,
        attachment_paths: list[str],
        start: float,
    ) -> dict[str, Any]:
        config = load_upload_config()
        validated = validate_attachments(attachment_paths, config)

        upload_start = time.monotonic()
        result = await upload_files(session.page, validated, config)
        upload_duration = time.monotonic() - upload_start

        meta: dict[str, Any] = {
            "attachment_count": len(validated),
            "attachment_names": [a.filename for a in validated],
            "attachment_types": [a.extension for a in validated],
            "attachment_categories": [a.category for a in validated],
            "attachment_mime_types": [a.mime_type for a in validated],
            "attachment_sizes": [a.size_bytes for a in validated],
            "total_attachment_bytes": sum(a.size_bytes for a in validated),
            "upload_duration_seconds": round(upload_duration, 2),
            "upload_method": result.get("method", "unknown"),
            "prompt_length": 0,
        }
        if result.get("method") == "text_inline":
            texts = result.get("text_contents", [])
            meta["inline_text_attachments"] = [t["filename"] for t in texts]
            meta["inline_text_contents"] = [t["content"] for t in texts]
        return meta

    async def reset_chat(self, session_id: str) -> None:
        if session_id == "all":
            for s in self._pool.list_sessions():
                sid = s["session_id"]
                session_obj = self._pool.get_session(sid)
                if session_obj is not None and session_obj.provider_name == "gemini":
                    await self._pool.reset(sid)
        else:
            await self._pool.reset(session_id)

    async def health_check(self) -> bool:
        try:
            session = await self._pool.acquire("gemini", "health-check", self._page_factory)
            try:
                await navigate_to_fresh_chat(session.page)
                health = await check_gemini_ready(session.page)
                raw = health.get("ready", False)
                return bool(raw)
            finally:
                await self._pool.release(session.session_id)
        except Exception:
            return False

    async def close_session(self, session_id: str) -> None:
        await self._pool.close(session_id)

    async def _ensure_fresh_chat(self, session: TabSession) -> None:
        await navigate_to_fresh_chat(session.page)
        import time as _time
        deadline = _time.monotonic() + 60.0
        while _time.monotonic() < deadline:
            health = await check_gemini_ready(session.page)
            if health.get("temporary_chat"):
                raise GeminiError("Gemini is in Temporary Chat mode")
            if health.get("ready"):
                return
            if health.get("needs_login"):
                detail = health.get("needs_login_detail", "")
                raise GeminiError(
                    f"User must log in to Gemini first. {detail}".strip()
                )
            await _async_sleep(1.0)
        raise GeminiError(
            "Timed out waiting for Gemini readiness. "
            "Open Chrome, navigate to gemini.google.com, log in, and try again."
        )

    async def detailed_health(self) -> dict[str, Any]:
        session = await self._pool.acquire("gemini", "detailed-health", self._page_factory)
        try:
            await navigate_to_fresh_chat(session.page)
            return await check_provider_health(session.page)
        finally:
            await self._pool.release(session.session_id)


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
