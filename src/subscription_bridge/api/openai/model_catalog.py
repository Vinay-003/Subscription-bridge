from __future__ import annotations

import importlib
from typing import Any

from subscription_bridge.api.openai_models import OpenAIModel
from subscription_bridge.utils.config import load_models_config

MODEL_FAKE = "subscription-bridge-fake"
MODEL_GEMINI_FAST = "subscription-bridge-gemini-fast"
MODEL_GEMINI_THINKING = "subscription-bridge-gemini-thinking"
MODEL_GEMINI_PRO = "subscription-bridge-gemini-pro"
MODEL_CHATGPT = "subscription-bridge-chatgpt"
MODEL_CHATGPT_THINKING = "subscription-bridge-chatgpt-thinking"
MODEL_CHATGPT_PRO = "subscription-bridge-chatgpt-pro"

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "subscription-bridge-gemini-flash": MODEL_GEMINI_FAST,
    "subscription-bridge-gemini-flash-lite": MODEL_GEMINI_FAST,
    "subscription-bridge-gemini-3-flash": MODEL_GEMINI_FAST,
    "gemini-2.0-flash": MODEL_GEMINI_FAST,
    "gemini-2.5-pro": MODEL_GEMINI_PRO,
}

DEFAULT_GEMINI_MODELS = {MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO}
DEFAULT_CHATGPT_MODELS = {MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO}
GEMINI_MODELS = DEFAULT_GEMINI_MODELS
CHATGPT_MODELS = DEFAULT_CHATGPT_MODELS

DEFAULT_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 32000,
    MODEL_GEMINI_FAST: 1_000_000,
    MODEL_GEMINI_THINKING: 192_000,
    MODEL_GEMINI_PRO: 1_000_000,
    MODEL_CHATGPT: 128_000,
    MODEL_CHATGPT_THINKING: 128_000,
    MODEL_CHATGPT_PRO: 128_000,
}

DEFAULT_MODEL_OUTPUT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 8192,
    MODEL_GEMINI_FAST: 8192,
    MODEL_GEMINI_THINKING: 65536,
    MODEL_GEMINI_PRO: 65536,
    MODEL_CHATGPT: 16384,
    MODEL_CHATGPT_THINKING: 16384,
    MODEL_CHATGPT_PRO: 16384,
}


def build_models() -> list[OpenAIModel]:
    config_models = _configured_models()
    if config_models:
        return [OpenAIModel(id=model_id, owned_by="subscription-bridge") for model_id in config_models]
    return [OpenAIModel(id=model_id, owned_by="subscription-bridge") for model_id in _default_model_ids()]


def strip_provider_prefix(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id


def resolve_model_alias(model_id: str) -> str:
    stripped = strip_provider_prefix(model_id)
    aliases = _configured_aliases() or DEFAULT_MODEL_ALIASES
    if stripped in aliases:
        return aliases[stripped]
    return model_id


def is_gemini_model(model_id: str) -> bool:
    return provider_for_model(model_id) == "gemini"


def is_chatgpt_model(model_id: str) -> bool:
    return provider_for_model(model_id) == "chatgpt"


def provider_for_model(model_id: str) -> str | None:
    model = strip_provider_prefix(resolve_model_alias(model_id))
    configured = _configured_models().get(model)
    if configured:
        provider = configured.get("provider")
        return str(provider) if provider else None
    if model == MODEL_FAKE:
        return "fake"
    if model in DEFAULT_GEMINI_MODELS:
        return "gemini"
    if model in DEFAULT_CHATGPT_MODELS:
        return "chatgpt"
    return None


def context_limit_for_model(model_id: str) -> int | None:
    model = strip_provider_prefix(resolve_model_alias(model_id))
    configured = _configured_models().get(model)
    if configured and configured.get("context_limit") is not None:
        return int(configured["context_limit"])
    return DEFAULT_MODEL_CONTEXT_LIMITS.get(model)


def output_limit_for_model(model_id: str) -> int | None:
    model = strip_provider_prefix(resolve_model_alias(model_id))
    configured = _configured_models().get(model)
    if configured and configured.get("output_limit") is not None:
        return int(configured["output_limit"])
    return DEFAULT_MODEL_OUTPUT_LIMITS.get(model)


def gemini_model_variant(model_id: str) -> str:
    variant = _configured_variant(model_id)
    if variant:
        return variant
    mapping = {
        MODEL_GEMINI_FAST: "Gemini 3 Flash",
        MODEL_GEMINI_THINKING: "Gemini 3 Deep Think",
        MODEL_GEMINI_PRO: "Gemini 3.1 Pro",
    }
    return mapping.get(strip_provider_prefix(model_id), "Gemini 3 Flash")


def chatgpt_model_variant(model_id: str) -> str:
    variant = _configured_variant(model_id)
    if variant:
        return variant
    mapping = {
        MODEL_CHATGPT: "Instant",
        MODEL_CHATGPT_THINKING: "Thinking",
        MODEL_CHATGPT_PRO: "Pro",
    }
    return mapping.get(strip_provider_prefix(model_id), "Instant")


def _configured_models() -> dict[str, dict[str, Any]]:
    data = load_models_config()
    raw_models = data.get("models", {})
    if not isinstance(raw_models, dict):
        return {}
    return {str(model_id): dict(raw or {}) for model_id, raw in raw_models.items() if isinstance(raw, dict)}


def _configured_aliases() -> dict[str, str]:
    data = load_models_config()
    raw_aliases = data.get("aliases", {})
    if not isinstance(raw_aliases, dict):
        return {}
    return {str(alias): str(target) for alias, target in raw_aliases.items()}


def _configured_variant(model_id: str) -> str | None:
    model = strip_provider_prefix(resolve_model_alias(model_id))
    configured = _configured_models().get(model)
    if configured and configured.get("provider_variant"):
        return str(configured["provider_variant"])
    return None


def _default_model_ids() -> list[str]:
    models = [MODEL_FAKE]
    if importlib.util.find_spec("subscription_bridge.providers.gemini"):
        models.extend([MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO])
    if importlib.util.find_spec("subscription_bridge.providers.chatgpt"):
        models.extend([MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO])
    return models
