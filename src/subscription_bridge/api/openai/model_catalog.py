from __future__ import annotations

import importlib

from subscription_bridge.api.openai_models import OpenAIModel

MODEL_FAKE = "subscription-bridge-fake"
MODEL_GEMINI_FAST = "subscription-bridge-gemini-fast"
MODEL_GEMINI_THINKING = "subscription-bridge-gemini-thinking"
MODEL_GEMINI_PRO = "subscription-bridge-gemini-pro"
MODEL_CHATGPT = "subscription-bridge-chatgpt"
MODEL_CHATGPT_THINKING = "subscription-bridge-chatgpt-thinking"
MODEL_CHATGPT_PRO = "subscription-bridge-chatgpt-pro"

MODEL_ALIASES: dict[str, str] = {
    "subscription-bridge-gemini-flash": MODEL_GEMINI_FAST,
    "subscription-bridge-gemini-flash-lite": MODEL_GEMINI_FAST,
    "subscription-bridge-gemini-3-flash": MODEL_GEMINI_FAST,
    "gemini-2.0-flash": MODEL_GEMINI_FAST,
    "gemini-2.5-pro": MODEL_GEMINI_PRO,
}

GEMINI_MODELS = {MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO}
CHATGPT_MODELS = {MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO}

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 32000,
    MODEL_GEMINI_FAST: 1_000_000,
    MODEL_GEMINI_THINKING: 192_000,
    MODEL_GEMINI_PRO: 1_000_000,
    MODEL_CHATGPT: 128_000,
    MODEL_CHATGPT_THINKING: 128_000,
    MODEL_CHATGPT_PRO: 128_000,
}

MODEL_OUTPUT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 8192,
    MODEL_GEMINI_FAST: 8192,
    MODEL_GEMINI_THINKING: 65536,
    MODEL_GEMINI_PRO: 65536,
    MODEL_CHATGPT: 16384,
    MODEL_CHATGPT_THINKING: 16384,
    MODEL_CHATGPT_PRO: 16384,
}


def build_models() -> list[OpenAIModel]:
    models = [OpenAIModel(id=MODEL_FAKE, owned_by="subscription-bridge")]
    if importlib.util.find_spec("subscription_bridge.providers.gemini"):
        for model_id in [MODEL_GEMINI_FAST, MODEL_GEMINI_THINKING, MODEL_GEMINI_PRO]:
            models.append(OpenAIModel(id=model_id, owned_by="subscription-bridge"))
    if importlib.util.find_spec("subscription_bridge.providers.chatgpt"):
        for model_id in [MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO]:
            models.append(OpenAIModel(id=model_id, owned_by="subscription-bridge"))
    return models


def strip_provider_prefix(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id


def resolve_model_alias(model_id: str) -> str:
    stripped = strip_provider_prefix(model_id)
    if stripped in MODEL_ALIASES:
        return MODEL_ALIASES[stripped]
    return model_id


def is_gemini_model(model_id: str) -> bool:
    return strip_provider_prefix(model_id) in GEMINI_MODELS


def is_chatgpt_model(model_id: str) -> bool:
    return strip_provider_prefix(model_id) in CHATGPT_MODELS


def gemini_model_variant(model_id: str) -> str:
    mapping = {
        MODEL_GEMINI_FAST: "Gemini 3 Flash",
        MODEL_GEMINI_THINKING: "Gemini 3 Deep Think",
        MODEL_GEMINI_PRO: "Gemini 3.1 Pro",
    }
    return mapping.get(strip_provider_prefix(model_id), "Gemini 3 Flash")


def chatgpt_model_variant(model_id: str) -> str:
    mapping = {
        MODEL_CHATGPT: "Instant",
        MODEL_CHATGPT_THINKING: "Thinking",
        MODEL_CHATGPT_PRO: "Pro",
    }
    return mapping.get(strip_provider_prefix(model_id), "Instant")
