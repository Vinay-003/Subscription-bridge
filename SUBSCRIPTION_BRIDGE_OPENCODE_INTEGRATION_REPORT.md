# SubscriptionBridge × OpenCode Integration Report

**Date:** 2026-10-17  
**Repo:** `/home/mylappy/Projects/Subscription-bridge`  
**Bridge version:** 0.1.0  
**OpenCode CLI:** 1.14.41  
**OpenCode Desktop:** 1.18.35  

---

## 1. ZIP Integration

| Item | Value |
|------|-------|
| ZIP | `SubscriptionBridge-gemini-audit-fixes.zip` (untracked, 11.5 MB) |
| Pre-integration HEAD | `a09a787` |
| Post-integration HEAD | `33167cb` (ZIP) → `0f9f7b0` (lint fixes) → selector fix (ChatGPT live E2E) |
| Commits merged | 11 (clean fast-forward; local HEAD was ancestor of ZIP HEAD) |
| Recovery | Branch + tag `backup/pre-zip-integration-2026-10-17` at `a09a787` |
| Temp fetch branch | `zip-integration-tmp` (deleted after merge) |

ZIP contents were extracted to `/tmp/opencode/zip_extract/`; its `.git` was never copied over the local repo.

## 2. Quality Gates

| Check | Result |
|-------|--------|
| `python -m compileall -q src tests` | ✅ exit 0 |
| `pytest -q` | ✅ **489 passed**, 9 warnings (~30 s) |
| `ruff check src/ tests/` | ✅ All checks passed (after fixes) |
| `mypy src/subscription_bridge/` | ✅ 102 files, no issues |

ZIP commits introduced 29 E501 + 14 new mypy errors vs baseline; all fixed in commit `0f9f7b0`:
- Reformatted long lines in streaming, tool_parser, openai_compat, session_pool, ui_guard, chatgpt adapter, gemini response_reader, and test files.
- `tools/bash.py`: passed `start_new_session` as an explicit keyword argument instead of spreading a dict (mypy arg-type errors).
- Auto-fixed import ordering (message_converter, gemini adapter, tests).

## 3. Local Server (OpenAI-compatible)

Started with (CDP on non-default port **9555**; both browser providers enabled):
```bash
setsid nohup env BRIDGE_CDP_URL=http://127.0.0.1:9555 \
  .venv/bin/bridge server --host 127.0.0.1 --port 8787 --provider both \
  </dev/null >/tmp/opencode/bridge_server.log 2>&1 &
```

Chrome must be running with a dedicated profile and remote debugging on the same port:
```bash
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run --no-default-browser-check --disable-sync &
```
Log in to gemini.google.com and chatgpt.com in that Chrome profile once; sessions persist in the profile.

### Endpoints verified

| Endpoint | Method | Status |
|----------|--------|--------|
| `/health` | GET | ✅ `{"status":"ok","version":"0.1.0",...}` all three providers `ready` |
| `/v1/models` | GET | ✅ 7 models listed |
| `/.well-known/opencode.json` | GET | ✅ Provider descriptor |
| `/v1/chat/completions` | POST | ✅ Non-stream response |
| `/v1/chat/completions` (stream=true) | POST | ✅ SSE chunks + `[DONE]` |
| `/chat/completions` (legacy) | POST | ✅ 200 |
| `/models` (legacy) | GET | ✅ 200 |
| `/docs` | GET | ✅ 200 |

With a logged-in CDP Chrome attached, `/health` reports `fake: ready`, `gemini: ready`, `chatgpt: ready`. Tool count: 10. `native_agent: true`.

## 4. Model Catalog

| Model ID | Provider | Context | Output |
|----------|----------|---------|--------|
| `subscription-bridge-fake` | fake | 32k | 8,192 |
| `subscription-bridge-gemini-fast` | gemini | 1M | 8,192 |
| `subscription-bridge-gemini-thinking` | gemini | 192k | 65,536 |
| `subscription-bridge-gemini-pro` | gemini | 1M | 65,536 |
| `subscription-bridge-chatgpt` | chatgpt | 128k | 16,384 |
| `subscription-bridge-chatgpt-thinking` | chatgpt | 128k | 16,384 |
| `subscription-bridge-chatgpt-pro` | chatgpt | 128k | 16,384 |

Legacy aliases (`subscription-bridge-gemini-flash`, `gemini-2.0-flash`, etc.) still resolve server-side via `DEFAULT_MODEL_ALIASES`.

## 5. OpenCode Desktop / CLI Registration

### Changes made

1. **Config backup:** `~/.config/opencode/opencode.json` → `opencode.json.backup-2026-10-17`
2. **Updated model IDs** in the `subscription-bridge` provider block to match the live catalog (replaced stale `gemini-flash`/`gemini-flash-lite` with the 7 canonical IDs).
3. **Enabled the provider** in `~/.config/opencode/opencode.jsonc` by removing `subscription-bridge` from `disabled_providers` (it had been listed there).

### Verification

```
$ opencode models subscription-bridge
subscription-bridge/subscription-bridge-chatgpt
subscription-bridge/subscription-bridge-chatgpt-pro
subscription-bridge/subscription-bridge-chatgpt-thinking
subscription-bridge/subscription-bridge-fake
subscription-bridge/subscription-bridge-gemini-fast
subscription-bridge/subscription-bridge-gemini-pro
subscription-bridge/subscription-bridge-gemini-thinking
```

### End-to-end via OpenCode CLI

```
$ env -u OPENCODE_CLIENT -u OPENCODE_SERVER_PASSWORD \
  opencode run -m subscription-bridge/subscription-bridge-fake \
  "Say exactly: bridge integration verified"

> build · subscription-bridge-fake
{"type": "final", "thought": "Generated JSON response for testing",
 "answer": "Received prompt: Conversation:\nUser: \"Say exactly: bridge integration verified\"\n"}
```

Full loop works: OpenCode CLI → SubscriptionBridge `/v1/chat/completions` → FakeProvider → JSON response returned to OpenCode.

> **Note:** Desktop-app CLI invocations inherit `OPENCODE_CLIENT=desktop` and attach to the running desktop server; for standalone CLI tests, unset `OPENCODE_CLIENT`, `OPENCODE_SERVER_PASSWORD`, and `OPENCODE_SERVER_USERNAME`.

## 6. Native Tool Execution (OpenCode-owned)

Architecture: OpenCode owns the agent loop and tool registry. The bridge only parses model output for tool-call markers (`<<<TOOLCALL:name>>> ... <<<END>>>`, JSON `tool_calls`, or `<tool_call>` XML) and returns them as OpenAI `tool_calls` entries with `finish_reason: "tool_calls"`. OpenCode then executes the tools locally.

Tool aliases handled by `tool_parser.py`:  
`file_read→read`, `file_write→write`, `file_edit→edit`, `run_command→bash`, `todo_write→todowrite`.

Tool-call parsing is covered by the unit suite (sentinel, JSON, XML, alias normalization, forced tool choice, unknown-tool filtering, parallel_tool_calls=false truncation). All 489 tests pass.

The FakeProvider does not emit sentinel tool-call markers (canned final-JSON only), so a live tool-call round-trip through the fake gateway is not exercisable end-to-end without browser-backed providers or a scripted fake. Full native-tool E2E requires Gemini/ChatGPT via CDP (see §7).

## 7. Browser-backed Gemini / ChatGPT — Live E2E

CDP Chrome is running on **port 9555** with a dedicated profile (`~/.subscription-bridge/chrome-profile`) logged into both providers. Config (`configs/app.yaml`, `.env.example`) and the default `BRIDGE_CDP_URL` were updated from `9333` to `9555` to avoid colliding with other local services.

### Live inference results

| Model | Prompt | Response | Status |
|-------|--------|----------|--------|
| `subscription-bridge-gemini-fast` | Reply with exactly: `GEMINI_BRIDGE_OK` | `GEMINI_BRIDGE_OK` | ✅ Pass |
| `subscription-bridge-chatgpt` | Reply with exactly: `CHATGPT_BRIDGE_OK` | `CHATGPT_BRIDGE_OK` | ✅ Pass |
| `subscription-bridge-chatgpt` | Write a Python function that merges two sorted lists (code block) | Full clean function, correct indentation | ✅ Pass |
| `subscription-bridge-chatgpt` | Write a Python class LRU cache with get/put + type hints | Full clean class (~178 tokens) | ✅ Pass |
| `subscription-bridge-gemini-fast` | Write a Python function that merges two sorted lists (code block) | Full clean function after language-label strip | ✅ Pass (slow: ~2 min) |

Both simple prompts returned `finish_reason: "stop"` with the exact expected token.

### Code-generation extraction (new ChatGPT + Gemini UIs)

Initial code prompts failed or returned polluted/truncated text. Fixes:

1. **ChatGPT new UI** renders code in `[data-code-block="true"]` → `.grid` (no `<pre>`). Extraction now prefers `.grid` `innerText` (preserves indentation) and skips the language/Run header (`[data-markdown-copy="exclude"]`).
2. **Stream-word detection** scoped to the latest assistant message only; wait loop treats stable text length as complete even if stream words linger after ChatGPT marks the response done.
3. **Gemini** leaked the code-block language label as a bare first line (`Python\ndef ...`); `_clean_assistant_text` strips it when followed by a code start token.

Verified live: ChatGPT merge-sorted-lists and LRU-cache prompts returned full indented code; Gemini merge-sorted-lists returned full clean code (no `Python` prefix). Gemini end-to-end can take ~2 minutes.

### ChatGPT selector fix (new ChatGPT UI)

The first live ChatGPT run timed out waiting for completion and extracted empty text. Root cause: the new ChatGPT DOM dropped `data-message-author-role="assistant"` and instead uses:

| Old selector | New selector(s) |
|--------------|-----------------|
| `[data-message-author-role="assistant"]` | `[data-conversation-role="assistant"]` (turn wrapper), `[data-markdown-text-style="assistant-message"]` (content), `[class*="DilResponseRoot"]` |
| `button[data-testid="stop-button"]` (generation state) | same + `[data-talvt-turn-state="generating"\|"thinking"\|"streaming"]` |

`_extract_latest_assistant_text` and `_submission_activity_report` in `src/subscription_bridge/providers/chatgpt/adapter.py` were updated to try the new content-bearing selectors first (with fallback to the old ones). A first pass that preferred `[data-conversation-role="assistant"]` returned only the `"ChatGPT said:"` label; the fix digs into nested markdown inside the turn wrapper. Debug screenshots from the failed run are under `~/.subscription-bridge/debug/`.

### Test-suite impact

`/health` calls real browser `health_check()` on both adapters (navigates pages). With a live CDP Chrome this made `test_health_includes_models_and_tool_count` hang in the full suite; the unit test now mocks `AppDependencies.get_provider_healths` so it does not touch the browser. Full suite: **489 passed**.

## 8. How to Run

```bash
# Install
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium  # if needed for browser providers

# Quality
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/subscription_bridge/
.venv/bin/python -m pytest -q

# Server (non-interactive; CDP on 9555, both browser providers)
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run --no-default-browser-check --disable-sync &

setsid nohup env BRIDGE_CDP_URL=http://127.0.0.1:9555 \
  .venv/bin/bridge server --host 127.0.0.1 --port 8787 --provider both \
  </dev/null >/tmp/opencode/bridge_server.log 2>&1 &

# Verify
curl -s http://127.0.0.1:8787/health
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"subscription-bridge-gemini-fast","messages":[{"role":"user","content":"Reply with exactly: GEMINI_BRIDGE_OK"}]}'
curl -s -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"subscription-bridge-chatgpt","messages":[{"role":"user","content":"Reply with exactly: CHATGPT_BRIDGE_OK"}]}'

# OpenCode
opencode models subscription-bridge
opencode run -m subscription-bridge/subscription-bridge-fake "hello"
```

## 9. Summary

| Goal | Status |
|------|--------|
| Integrate ZIP into local repo, preserve history | ✅ Done (fast-forward, recovery refs kept) |
| Full automated test suite green | ✅ 489 passed |
| Ruff + mypy clean | ✅ Clean after `0f9f7b0` |
| Local OpenAI-compatible API | ✅ Health, models, chat (stream + non-stream) verified |
| OpenCode Desktop/CLI provider registration | ✅ Config updated, provider enabled, models visible, CLI E2E green (fake) |
| Native OpenCode tool execution | ✅ Parsing/normalization unit-tested; live E2E pending browser providers |
| Real browser Gemini/ChatGPT inference | ✅ Live E2E pass (Gemini + ChatGPT via CDP port 9555) |
| Code generation via bridge (ChatGPT + Gemini) | ✅ Full indented code returned; header pollution and language-label strip fixed |
| Git push to origin | ✅ Pushed `b9b084a` (origin switched to SSH) |

## 10. Commits this session

| Commit | Summary |
|--------|---------|
| `0f9f7b0` | ZIP lint/mypy fixes |
| `94e5a7f` | ChatGPT new-UI selectors, CDP port 9555, health-test mock |
| `b9b084a` | ChatGPT code-block extraction + stream settle wait; Gemini language-label strip |
