from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.openai_compat import router as openai_router
from subscription_bridge.api.routes import router
from subscription_bridge.core.errors import ParserError


class _Lifespan:
    def __init__(self, deps: AppDependencies) -> None:
        self._deps = deps
        self._init_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> None:
        import os

        provider = os.environ.get("BRIDGE_INIT_PROVIDERS")
        if provider is None:
            return None
        if provider in ("gemini", "both"):
            print("  ⏳  Waiting for Gemini login in Chrome...", flush=True)
            self._init_task = asyncio.create_task(self._wait_for_gemini())
        if provider == "chatgpt":
            print("  ⏳  Waiting for ChatGPT login in Chrome...", flush=True)

        return None

    async def __aexit__(self, *exc_info: object) -> bool:
        if self._init_task is not None and not self._init_task.done():
            self._init_task.cancel()
            try:
                await self._init_task
            except (asyncio.CancelledError, Exception):
                pass
        exc = exc_info[1] if exc_info[0] is not None else None
        try:
            await self._deps.shutdown()
        except asyncio.CancelledError:
            pass
        if isinstance(exc, asyncio.CancelledError):
            return True
        return False

    async def _wait_for_gemini(self) -> None:
        try:
            adapter = await self._deps.get_gemini_adapter()
            while True:
                ok = await adapter.health_check()
                if ok:
                    print("  ✓ Gemini ready", flush=True)
                    return
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"  ✗ Gemini: {e}", flush=True)


def create_app() -> FastAPI:
    deps = AppDependencies()
    deps.load_config()

    app = FastAPI(
        title="SubscriptionBridge API",
        description="Local personal agent runtime for browser-based LLMs. "
                    "Supports OpenAI-compatible /v1 endpoints for OpenCode integration.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lambda app: _Lifespan(deps),
    )
    app.state.deps = deps

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(openai_router)

    @app.exception_handler(ParserError)
    async def parser_error_handler(request: Request, exc: ParserError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc), "error_type": "parser_error"},
        )

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_type": type(exc).__name__},
        )

    return app


app = create_app()
