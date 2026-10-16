# SubscriptionBridge — Gemini Audit Follow-up Implementation Report

**Baseline:** uploaded `SubscriptionBridge-fixed.zip`, branch `main` at `d110ee6`  
**Final branch:** `main`  
**Scope:** implement the additional issues and compatibility items from `subscription_bridge_audit_and_plan.md` while retaining the previous commits.

## Summary

Implemented the majority of the Gemini plan's actionable source changes: schema-aware tool aliases and required bash descriptions; tolerant sentinel parsing; false-positive JSON protection; 24,000-character tool-result capacity; full-transcript recovery for fresh browser chats; preservation of `<env>` and `<available_skills>` during prompt compaction; CDP visible-tab reuse and safe disconnect; Gemini per-request response freshness checks; ChatGPT assistant-only message counting and parameterized composer insertion; nullable/extended OpenAI request fields; SSE null-field omission and optional usage chunks; route aliases; JSON response-format guidance; and optional single-tool behavior.

ChatGPT provider configuration is enabled and points to `https://chatgpt.com`. Browser mode includes `reuse_open_tab: true`. The persistent browser response style system prompt continues to request concise plain text or ordinary Markdown, without HTML pages, interactive widgets, embedded apps, or unnecessary commentary.

## Changes made

### Tool parsing and messages
- Added schema-checked tool-name aliases: `file_read`, `file_write`, `file_edit`, `run_command`, and `todo_write`.
- Added schema-aware parameter aliases for `path`, `file_path`, `old_string`, and `new_string` when the target schema declares the canonical property.
- Synthesized a concise required `bash.description` only when the supplied schema requires it.
- Made sentinel markers tolerant of whitespace, case, inline argument values, and a missing final `<<<END>>>`.
- Removed leading `Copy code` noise and prevented ordinary JSON objects with only a `name` field (such as package manifests) from automatically becoming tool calls.
- Increased tool-result text capacity from 1,000 to 24,000 characters.
- Added a `full_history` message-conversion option. The gateway attaches the full normalized transcript as recovery metadata; providers use it when starting a fresh browser chat and use incremental turns when continuing an existing browser conversation.
- Preserved `<env>` and `<available_skills>` blocks when compacting the OpenCode system prompt.

### Browser and provider behavior
- Added configurable `reuse_open_tab` handling, provider-tab focus, and an unclaimed blank-tab fallback in CDP mode.
- Avoided explicitly closing the externally managed CDP context/browser on shutdown.
- Reset active-conversation/model flags when an idle tab is assigned to a different conversation.
- Removed `new chat` from the global unsafe labels and excluded explicitly requested labels from the unsafe-word filter.
- Gemini now counts response elements without duplicate selector counts, recognizes `/app/<id>` and `/u/<n>/app` routes, requires a response newer than the pre-send count, and waits for response text to stabilize before declaring completion.
- ChatGPT activity detection counts only assistant-role messages and detects `button[data-testid="stop-button"]`.
- ChatGPT composer insertion now passes prompt text as an evaluation argument rather than interpolating it into JavaScript source, then verifies the inserted text. An already-open, empty ChatGPT tab is reused in place.

### API compatibility
- Added nullable `temperature` and `max_tokens`, plus `max_completion_tokens`, `stream_options`, `parallel_tool_calls`, `response_format`, and `reasoning_effort` request fields.
- Added `/models` and `/chat/completions` aliases alongside the `/v1` routes.
- Added `stream_options.include_usage` output and omitted null fields from SSE delta serialization.
- Honored `parallel_tool_calls: false` by returning at most one parsed tool call.
- Added a JSON-only system instruction for `response_format: {"type":"json_object"}`.
- Enabled ChatGPT in `configs/providers.yaml` and updated its URL to `https://chatgpt.com`.

## Git commits

The existing four commits from the earlier delivery are preserved. These follow-up changes are split into reviewable commits:

- `88a5079` — `fix: harden OpenAI tool protocol and request compatibility`
- `856f911` — `fix: complete visible tab reuse and conversation reset handling`
- `336454a` — `fix: detect fresh browser responses and preserve composer input`
- `da6ad5e` — `test: cover Gemini audit follow-ups and enable ChatGPT provider`
- `290d524` — `fix: restore full transcript for fresh Gemini conversations`
- `75aab7e` — `fix: honor JSON response format and parallel tool preference`

## Verification

- Python compilation: passed (`python -m compileall -q src tests`).
- Git whitespace check: passed (`git diff --check`).
- Full unit suite: **489 passed**.
- Added seven targeted tests for aliases/defaults, tolerant sentinel parsing, JSON false positives, UI guard, prompt compaction, long tool results, and request compatibility.

### Environment qualification

The environment does not have `structlog` installed and could not access the package index. Tests were run with a temporary, external `structlog` compatibility stub placed under `/tmp`; the stub is not included in the repository or ZIP. This is a useful regression result but is not the same as running against the project's full installed dependency set. Ruff/mypy and live browser verification were not run.

## Remaining verification limitations

- No authenticated Chrome session was available here, so ChatGPT/Gemini DOM selectors, model submission, and real multi-turn tool execution have not been verified end-to-end against the current live websites.
- OpenAI compatibility fields are accepted and the specific implemented behaviors above are handled; `reasoning_effort` is accepted as metadata but does not currently control a provider-specific reasoning setting.
- UI automation can still be affected by future provider UI changes. Run a manual smoke test with a logged-in browser before relying on this build.

## Suggested manual smoke test

1. Start Chrome with CDP on port 9333 using a dedicated profile and log into Gemini and ChatGPT.
2. Keep a provider tab open and start SubscriptionBridge in CDP mode.
3. From OpenCode, ask for a small file edit requiring at least two tool calls and a tool result between them.
4. Verify the browser shows the request and latest response, the second turn sees the original task and tool result, and OpenCode (not SubscriptionBridge) executes the tools.
5. Run two separate OpenCode sessions and confirm their browser conversations do not mix.
6. Stop the bridge and confirm the external Chrome window and tabs remain open.
