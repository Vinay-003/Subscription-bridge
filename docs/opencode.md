# SubscriptionBridge — OpenCode Integration

## Overview

SubscriptionBridge exposes an OpenAI-compatible API at `/v1` so that
[OpenCode](https://opencode.ai) and other OpenAI-compatible clients can use
browser-based LLMs (Gemini, ChatGPT) through SubscriptionBridge.

**Architecture when connected to OpenCode:**

- **OpenCode** is the coding agent — it handles project context, tools, file edits,
  shell commands, and code patches.
- **SubscriptionBridge** is the model/backend bridge — it receives chat completion
  requests from OpenCode and forwards them to the browser-based provider.

---

## OpenCode Configuration

Add the following to your OpenCode configuration (e.g., `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "subscription-bridge": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "SubscriptionBridge Local",
      "options": {
        "baseURL": "http://127.0.0.1:8787/v1",
        "apiKey": "dummy"
      },
      "models": {
        "subscription-bridge-fake": {
          "name": "SubscriptionBridge Fake",
          "limit": { "context": 32000, "output": 8192 }
        },

        "subscription-bridge-gemini-flash-lite": {
          "name": "Gemini 3.5 Flash-Lite",
          "limit": { "context": 1048576, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true,
          "reasoning": true,
          "variants": {
            "low":    { "reasoningEffort": "low" },
            "medium": { "reasoningEffort": "medium" },
            "high":   { "reasoningEffort": "high" }
          }
        },
        "subscription-bridge-gemini-flash": {
          "name": "Gemini 3.8 Flash",
          "limit": { "context": 1048576, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true,
          "reasoning": true,
          "variants": {
            "low":    { "reasoningEffort": "low" },
            "medium": { "reasoningEffort": "medium" },
            "high":   { "reasoningEffort": "high" }
          }
        },
        "subscription-bridge-gemini-pro": {
          "name": "Gemini 3.1 Pro",
          "limit": { "context": 1000000, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true,
          "reasoning": true,
          "variants": {
            "low":    { "reasoningEffort": "low" },
            "medium": { "reasoningEffort": "medium" },
            "high":   { "reasoningEffort": "high" }
          }
        },
        "subscription-bridge-gemini-argon": {
          "name": "Gemini 4 Argon",
          "limit": { "context": 983040, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true,
          "reasoning": true,
          "variants": {
            "low":    { "reasoningEffort": "low" },
            "medium": { "reasoningEffort": "medium" },
            "high":   { "reasoningEffort": "high" }
          }
        },

        "subscription-bridge-chatgpt": {
          "name": "ChatGPT Instant",
          "limit": { "context": 128000, "output": 8192 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true
        },

        "subscription-bridge-chatgpt-thinking": {
          "name": "ChatGPT Thinking",
          "limit": { "context": 128000, "output": 8192 },
          "modalities": { "input": ["text", "image"], "output": ["text"] },
          "tool_call": true
        }
      }
    }
  }
}
```

### Compaction Config

Recommended to include with OpenCode:

```json
{
  "compaction": {
    "auto": true,
    "prune": true,
    "reserved": 100000
  }
}
```

OpenCode owns context, session history, tools, and tool execution. SubscriptionBridge
keeps a browser conversation tied to a stable conversation key and serializes requests
to that tab. Distinct conversation keys never borrow an idle tab from another session.
The provider browser should remain visible; CDP mode reuses an existing matching provider
tab for the first session and creates a separate tab for another isolated conversation.

---

## Subagent Model Mapping

OpenCode can use different models for different agent types.
Recommended configuration:

| Agent Role  | Gemini Option                      | ChatGPT Option                   |
|-------------|------------------------------------|----------------------------------|
| `build`     | `subscription-bridge-gemini-flash` | `subscription-bridge-chatgpt`    |
| `plan`      | `subscription-bridge-gemini-pro`   | `subscription-bridge-chatgpt`    |
| `explore`   | `subscription-bridge-gemini-flash-lite` | `subscription-bridge-chatgpt` |
| `review`    | `subscription-bridge-gemini-pro`   | `subscription-bridge-chatgpt`    |

SubscriptionBridge does not implement subagents. OpenCode manages agents.

### Thinking level variants

Models with a `"variants"` object get a reasoning-effort dropdown in the OpenCode model
picker. Each variant maps to a `reasoningEffort` value (`low` / `medium` / `high`), which
SubscriptionBridge reads from the request and applies as the Gemini **Thinking level** in
the browser model picker before sending the prompt. The top-level `"reasoning": true`
flag marks the model as reasoning-capable; the `variants` entries are what actually
produce the selectable efforts. Without a matching effort, the browser keeps its last
thinking level.

Recommended `variants` block (identical for all four Gemini models):

```json
"variants": {
  "low":    { "reasoningEffort": "low" },
  "medium": { "reasoningEffort": "medium" },
  "high":   { "reasoningEffort": "high" }
}
```

ChatGPT has no model picker or granular thinking-level control in its web UI — only a
composer **Think** toggle button. `subscription-bridge-chatgpt-thinking` maps to turning
that toggle **on**, and the other ChatGPT models map to turning it **off**, so each model
is a separate entry rather than a `reasoning: true` variant.

---

## Setup Steps

### Option A: Gemini

```bash
# 1. Start Chrome with remote debugging on port 9555
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync

# 2. Navigate to https://gemini.google.com/app and log in manually

# 3. Start the bridge server
BRIDGE_CDP_URL=http://127.0.0.1:9555 bridge server --host 127.0.0.1 --port 8787 --provider gemini

# 4. Verify models
curl http://127.0.0.1:8787/v1/models

# 5. Select a Gemini model in OpenCode
```

### Option B: ChatGPT

```bash
# 1. Start Chrome with remote debugging on port 9555
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync

# 2. Navigate to https://chatgpt.com and log in manually

# 3. Start the bridge server
BRIDGE_CDP_URL=http://127.0.0.1:9555 bridge server --host 127.0.0.1 --port 8787 --provider chatgpt

# 4. Verify models
curl http://127.0.0.1:8787/v1/models

# 5. Select the ChatGPT model in OpenCode
```

### Option C: Both (or use the script)

```bash
# One-command startup (Chrome + server)
./start.sh both

# Or start manually:
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run --no-default-browser-check --disable-sync &

BRIDGE_CDP_URL=http://127.0.0.1:9555 bridge server --host 127.0.0.1 --port 8787 --provider both

# Or let the server prompt you
bridge server
# ? Which provider do you want to use?
#   1) Gemini
#   2) ChatGPT
#   3) Both
```

---

## Model Reference

| Model ID | Backend | Context | Output | Browser Required |
|----------|---------|---------|--------|-----------------|
| `subscription-bridge-fake` | FakeProviderAdapter | 32K | 8K | No |
| `subscription-bridge-gemini-flash-lite` | Gemini 3.5 Flash-Lite | 1M | 64K | Yes |
| `subscription-bridge-gemini-flash` | Gemini 3.8 Flash | 1M | 64K | Yes |
| `subscription-bridge-gemini-pro` | Gemini 3.1 Pro | 1M | 64K | Yes |
| `subscription-bridge-gemini-argon` | Gemini 4 Argon | 960K | 64K | Yes |
| `subscription-bridge-chatgpt` | ChatGPT Instant | 128K | 8K | Yes |
| `subscription-bridge-chatgpt-thinking` | ChatGPT Thinking | 128K | 8K | Yes |
| `subscription-bridge-chatgpt-pro` | ChatGPT Pro | 128K | 8K | Yes |

Legacy ids (`subscription-bridge-gemini-fast`, `subscription-bridge-gemini-thinking`)
are still accepted as aliases and resolve to `gemini-flash` and `gemini-pro`.

When OpenCode compacts a session (the re-sent history shrinks), SubscriptionBridge
detects the rewrite and restarts the browser chat with the full post-compaction
transcript, so browser context stays consistent with OpenCode's compacted view.
The system prompt is **not** re-sent in full: the browser receives a short reminder
(a bounded slice of the operating rules plus the tool contract) so the summary turn
does not re-inject the entire initial prompt into an already compacted context.

On the first turn of a conversation the system prompt is delivered as two labelled
sections when a boundary exists between them: `<context_overview>` (identity, env,
skills) and `<operating_instructions>` (tools and rules).

Long generations stream `: keepalive` SSE comments every 10 s, and the browser
response wait follows the budget table in `docs/configuration.md`, so slow Argon/Pro
turns are no longer cut off at a fixed 120 s.

---

## Tool-Call Compatibility

SubscriptionBridge supports OpenAI tool calls in the following way:

1. **Tools are accepted** in `/v1/chat/completions` requests
2. **Tools and their complete JSON Schemas are sent** in bridge prompt instructions.
   Browser models use a delimiter-based format for robust multiline arguments; ordinary
   JSON tool-call responses are also accepted.
3. **The model output is parsed, validated against the tools on the current request,**
   and converted to OpenAI-compatible `tool_calls` in the response
4. **Tool results** from OpenCode (`role: "tool"`) are converted into readable
   transcript entries in the prompt
5. **SubscriptionBridge does not execute** tools when used via OpenCode — OpenCode handles execution

When the model decides to call a tool, the response contains:
```json
{
  "choices": [{
    "finish_reason": "tool_calls",
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_1",
        "type": "function",
        "function": {
          "name": "tool_name",
          "arguments": "{\"arg\": \"value\"}"
        }
      }]
    }
  }]
}
```

---

## Known Limitations

- **Tool call reliability**: Browser models are prompted to emit delimiter-based calls,
  which are then schema-checked and type-coerced. This remains less deterministic than
  native API function calling; malformed calls are rejected rather than passed to OpenCode.
- **Streaming is simulated**: True token-by-token streaming from the browser
  provider is not available. Completed response text/tool calls are chunked into SSE events.
- **Token counts are approximate**: Uses character count / 4, not a real tokenizer.
- **Context limit is approximate**: Based on estimated tokens. If exceeded, the
  API returns `context_length_exceeded` — OpenCode compaction handles this.
- **Browser latency**: Responses are slower than API-based models.
- **No multimodal**: Image inputs in content arrays are accepted but ignored.
- **API key**: Any value works (e.g., `"dummy"`). The server does not validate.

### Browser conversation recovery and plain-text responses

The OpenAI-compatible gateway stores the full normalized OpenCode transcript in request metadata as a recovery prompt. Providers use it only when a browser conversation is new or has been reset; continuing conversations receive the incremental message tail to avoid duplicating history. Browser-facing system instructions request concise plain text or ordinary Markdown and discourage HTML pages, interactive widgets, embedded apps, and unnecessary commentary.

For visible-tab operation, configure `browser.mode: cdp` and `browser.reuse_open_tab: true` in `configs/app.yaml`. The bridge claims an unallocated tab for the requested provider and disconnects from CDP on shutdown without explicitly closing the external Chrome context. ChatGPT is enabled in `configs/providers.yaml` by default; log in to the provider in the Chrome profile before using it.

The OpenAI-compatible API is available at `/v1/chat/completions` and `/v1/models`; `/chat/completions` and `/models` aliases are also provided. Streaming requests support `stream_options: {"include_usage": true}`.
