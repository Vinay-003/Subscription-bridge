from __future__ import annotations

import importlib.util as importlib_util
from typing import Any

from subscription_bridge.api.openai_models import OpenAIModel
from subscription_bridge.utils.config import load_models_config

MODEL_FAKE = "subscription-bridge-fake"

# Gemini web UI models (current naming as of 2026-10).
MODEL_GEMINI_FLASH_LITE = "subscription-bridge-gemini-flash-lite"
MODEL_GEMINI_FLASH = "subscription-bridge-gemini-flash"
MODEL_GEMINI_PRO = "subscription-bridge-gemini-pro"
MODEL_GEMINI_ARGON = "subscription-bridge-gemini-argon"

# Legacy Gemini model ids kept as aliases for older configs.
MODEL_GEMINI_FAST = "subscription-bridge-gemini-fast"
MODEL_GEMINI_THINKING = "subscription-bridge-gemini-thinking"

MODEL_CHATGPT = "subscription-bridge-chatgpt"
MODEL_CHATGPT_THINKING = "subscription-bridge-chatgpt-thinking"
MODEL_CHATGPT_PRO = "subscription-bridge-chatgpt-pro"

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "subscription-bridge-gemini-fast": MODEL_GEMINI_FLASH,
    "subscription-bridge-gemini-thinking": MODEL_GEMINI_PRO,
    "subscription-bridge-gemini-3-flash": MODEL_GEMINI_FLASH,
    "subscription-bridge-gemini-3-flash-lite": MODEL_GEMINI_FLASH_LITE,
    "subscription-bridge-gemini-3-pro": MODEL_GEMINI_PRO,
    "gemini-2.0-flash": MODEL_GEMINI_FLASH_LITE,
    "gemini-2.5-pro": MODEL_GEMINI_PRO,
}

DEFAULT_GEMINI_MODELS = {
    MODEL_GEMINI_FLASH_LITE,
    MODEL_GEMINI_FLASH,
    MODEL_GEMINI_PRO,
    MODEL_GEMINI_ARGON,
}
DEFAULT_CHATGPT_MODELS = {MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO}
GEMINI_MODELS = DEFAULT_GEMINI_MODELS
CHATGPT_MODELS = DEFAULT_CHATGPT_MODELS

DEFAULT_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 32000,
    MODEL_GEMINI_FLASH_LITE: 1_048_576,
    MODEL_GEMINI_FLASH: 1_048_576,
    MODEL_GEMINI_PRO: 1_000_000,
    MODEL_GEMINI_ARGON: 1_048_576,
    MODEL_CHATGPT: 128_000,
    MODEL_CHATGPT_THINKING: 131_072,
    MODEL_CHATGPT_PRO: 128_000,
}

DEFAULT_MODEL_OUTPUT_LIMITS: dict[str, int] = {
    MODEL_FAKE: 8192,
    MODEL_GEMINI_FLASH_LITE: 16384,
    MODEL_GEMINI_FLASH: 65536,
    MODEL_GEMINI_PRO: 65536,
    MODEL_GEMINI_ARGON: 65536,
    MODEL_CHATGPT: 16384,
    MODEL_CHATGPT_THINKING: 131072,
    MODEL_CHATGPT_PRO: 16384,
}

DEFAULT_MODEL_REASONING_LEVELS: dict[str, list[str]] = {
    MODEL_GEMINI_FLASH_LITE: ["low", "medium", "high"],
    MODEL_GEMINI_FLASH: ["low", "medium", "high"],
    MODEL_GEMINI_PRO: ["low", "medium", "high"],
    MODEL_GEMINI_ARGON: ["low", "medium", "high"],
    MODEL_CHATGPT_THINKING: ["low", "medium", "high"],
}


def build_models() -> list[OpenAIModel]:
    """Return an OpenAI-compatible model catalog without bridge-native tools.

    Tool definitions belong on each chat-completions request; OpenCode owns its
    tool registry and execution loop. Native bridge routes keep their own tools.
    Each model carries context_window/max_output_tokens so clients that rely on
    the models endpoint (not just opencode.json) can budget tokens and compaction.
    """
    config_models = _configured_models()
    model_ids = list(config_models) if config_models else _default_model_ids()
    return [_model_entry(model_id, config_models.get(model_id, {})) for model_id in model_ids]


def _model_entry(model_id: str, cfg: dict[str, Any]) -> OpenAIModel:
    context_limit = int(cfg.get("context_limit") or DEFAULT_MODEL_CONTEXT_LIMITS.get(model_id, 131072))
    output_limit = int(cfg.get("output_limit") or DEFAULT_MODEL_OUTPUT_LIMITS.get(model_id, 16384))
    levels = reasoning_levels_for_model(model_id)
    return OpenAIModel(
        id=model_id,
        owned_by="subscription-bridge",
        context_window=context_limit,
        max_output_tokens=output_limit,
        reasoning=bool(levels),
        reasoning_efforts=levels,
    )


def build_native_tool_definitions() -> list[dict[str, Any]]:
    from subscription_bridge.tools import (
        BashTool,
        CodebaseSearchTool,
        FileEditTool,
        FileReadTool,
        FileWriteTool,
        GitDiffTool,
        GlobTool,
        GrepTool,
        PatchTool,
        TodoWriteTool,
    )

    native_tools = [
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GrepTool(),
        GlobTool(),
        BashTool(),
        PatchTool(),
        GitDiffTool(),
        CodebaseSearchTool(),
        TodoWriteTool(),
    ]

    definitions: list[dict[str, Any]] = []
    for tool in native_tools:
        definitions.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema if tool.input_schema else {"type": "object", "properties": {}},
            },
        })
    return definitions


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


def reasoning_levels_for_model(model_id: str) -> list[str]:
    """Reasoning effort levels a model accepts (empty list = no reasoning).

    Configured ``reasoning_efforts`` wins; otherwise the default table applies.
    These are the low/medium/high options OpenCode surfaces as a dropdown when
    a model declares ``variants`` for each effort.
    """
    model = strip_provider_prefix(resolve_model_alias(model_id))
    configured = _configured_models().get(model)
    if configured:
        if configured.get("reasoning") is False:
            return []
        efforts = configured.get("reasoning_efforts")
        if isinstance(efforts, list) and efforts:
            return [str(level).lower() for level in efforts]
        if configured.get("reasoning") is True:
            return DEFAULT_MODEL_REASONING_LEVELS.get(model, ["low", "medium", "high"])
    return list(DEFAULT_MODEL_REASONING_LEVELS.get(model, []))


def gemini_model_variant(model_id: str) -> str:
    variant = _configured_variant(model_id)
    if variant:
        return variant
    mapping = {
        MODEL_GEMINI_FLASH_LITE: "3.5 Flash-Lite",
        MODEL_GEMINI_FLASH: "3.8 Flash",
        MODEL_GEMINI_PRO: "3.1 Pro",
        MODEL_GEMINI_ARGON: "4 Argon",
    }
    resolved = strip_provider_prefix(resolve_model_alias(model_id))
    return mapping.get(resolved, "3.8 Flash")


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
    if importlib_util.find_spec("subscription_bridge.providers.gemini"):
        models.extend([
            MODEL_GEMINI_FLASH_LITE,
            MODEL_GEMINI_FLASH,
            MODEL_GEMINI_PRO,
            MODEL_GEMINI_ARGON,
        ])
    if importlib_util.find_spec("subscription_bridge.providers.chatgpt"):
        models.extend([MODEL_CHATGPT, MODEL_CHATGPT_THINKING, MODEL_CHATGPT_PRO])
    return models
