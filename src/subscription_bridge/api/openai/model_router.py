from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from subscription_bridge.api.dependencies import AppDependencies
from subscription_bridge.api.openai.model_catalog import (
    MODEL_FAKE,
    chatgpt_model_variant,
    gemini_model_variant,
    provider_for_model,
    strip_provider_prefix,
)


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    variant: str | None = None


def route_for_model(model_id: str) -> ModelRoute | None:
    provider = provider_for_model(model_id)
    if provider is None:
        return None
    if provider == "gemini":
        return ModelRoute(provider=provider, variant=gemini_model_variant(model_id))
    if provider == "chatgpt":
        return ModelRoute(provider=provider, variant=chatgpt_model_variant(model_id))
    return ModelRoute(provider=provider)


async def resolve_adapter(model_id: str, deps: AppDependencies) -> Any | None:
    route = route_for_model(model_id)
    if route is None:
        return None
    if route.provider == "fake" or strip_provider_prefix(model_id) == MODEL_FAKE:
        return deps.get_registry().get("fake")
    if route.provider == "gemini":
        try:
            return await deps.get_gemini_adapter()
        except Exception:
            return None
    if route.provider == "chatgpt":
        try:
            return await deps.get_chatgpt_adapter()
        except Exception:
            return None
    return None


def prompt_with_model_hint(prompt: str, model_id: str) -> str:
    route = route_for_model(model_id)
    if route is None or route.variant is None:
        return prompt
    header = f"[Model: {route.variant}]"
    if not prompt:
        return header
    return f"{header}\n{prompt}"


def provider_metadata(model_id: str) -> dict[str, str | None]:
    route = route_for_model(model_id)
    return {
        "gemini_model_variant": route.variant if route and route.provider == "gemini" else None,
        "chatgpt_model_variant": route.variant if route and route.provider == "chatgpt" else None,
    }
