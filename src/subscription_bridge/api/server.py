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

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc_info: object) -> bool:
        exc = exc_info[1] if exc_info[0] is not None else None
        try:
            await self._deps.shutdown()
        except asyncio.CancelledError:
            pass
        if isinstance(exc, asyncio.CancelledError):
            return True
        return False


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
