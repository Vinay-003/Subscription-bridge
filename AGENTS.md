# SubscriptionBridge - Coding Agent Guide

## Project Overview

SubscriptionBridge is a local personal agent runtime that turns browser-based consumer LLM subscriptions (Gemini, ChatGPT, Claude) into agent-capable inference backends. The browser LLM is NOT the agent — the local runtime is the agent, and the browser UI is only a provider/inference backend.

## Architecture (6 Layers)

1. **CLI/API** - User entry point (Typer CLI + FastAPI)
2. **Agent Runtime** - Loop: plan → reason → act → observe
3. **Context Builder** - Builds prompts with token budget control
4. **Provider Layer** - Standard interface for Gemini/ChatGPT/Claude
5. **Browser Runtime** - Playwright lifecycle, tab sessions, selector safety
6. **Tools & Memory** - File ops, grep, bash, codebase indexing

## Implementation Phases

| Phase | What | Status |
|-------|------|--------|
| 0 | Repo bootstrap, config, logger, CLI shell | ✅ Done |
| 1 | Provider interface, FakeProvider, Registry | ✅ Done |
| 2 | Browser runtime (Playwright, sessions, selectors) | ✅ Done |
| 3 | Gemini text provider (fresh chat, prompt IO, response) | ✅ Done |
| 4 | Agent runtime + tool loop + JSON parser | ✅ Done |
| 5 | Codebase memory (indexer, embeddings, retriever) | ✅ Done |
| 6 | Gemini file prompting (upload + attachments) | ✅ Done |
| 7 | Local FastAPI server | ✅ Done |
| 8 | Polish, README, docs, examples, demo | ✅ Done |
| 9 | OpenCode / OpenAI-compatible API | ⬜ Next |

## Key Patterns

- **ProviderAdapter**: All browser model calls go through `ProviderAdapter.send_prompt()`
- **ProviderRequest/Response**: Standard dataclasses, no provider-specific types in core
- **Browser Runtime**: All browser interactions through `PlaywrightManager`/`SessionPool`
- **Selectors in YAML**: Never hardcoded — `configs/selectors/{provider}.yaml`
- **ToolExecutor**: All tool calls validated, logged, and time-limited
- **JSON Parser**: Strict parsing with repair fallbacks for unreliable browser output

## Code Quality

- Full typing required everywhere
- No hardcoded selectors
- All external actions have retries and timeouts
- Every provider failure produces debug screenshots/logs
- Tests required for every phase
- Run `ruff check` and `mypy` before marking phase complete

## Commands

```bash
# Install
pip install -e ".[dev]"
playwright install chromium

# Test
pytest tests/ -v
pytest tests/ --cov=src/subscription_bridge --cov-report=term-missing

# Lint
ruff check src/ tests/
mypy src/subscription_bridge/

# Run
bridge --help
bridge ask "hello" --provider fake
bridge provider list
bridge codebase index .
bridge codebase search "provider adapter" -w . -k 5
bridge server --host 127.0.0.1 --port 8787
```
