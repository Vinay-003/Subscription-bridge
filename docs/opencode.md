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

        "subscription-bridge-gemini-fast": {
          "name": "Gemini 3 Flash",
          "limit": { "context": 1000000, "output": 8192 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        },
        "subscription-bridge-gemini-thinking": {
          "name": "Gemini 3 Deep Think",
          "limit": { "context": 192000, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        },
        "subscription-bridge-gemini-pro": {
          "name": "Gemini 3.1 Pro",
          "limit": { "context": 1000000, "output": 65536 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        },

        "subscription-bridge-chatgpt": {
          "name": "ChatGPT",
          "limit": { "context": 128000, "output": 16384 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
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
| `build`     | `subscription-bridge-gemini-pro`   | `subscription-bridge-chatgpt`    |
| `plan`      | `subscription-bridge-gemini-thinking` | `subscription-bridge-chatgpt` |
| `explore`   | `subscription-bridge-gemini-fast`  | `subscription-bridge-chatgpt`    |
| `review`    | `subscription-bridge-gemini-pro`   | `subscription-bridge-chatgpt`    |

SubscriptionBridge does not implement subagents. OpenCode manages agents.

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
| `subscription-bridge-gemini-fast` | Gemini 3 Flash | 1M | 8K | Yes |
| `subscription-bridge-gemini-thinking` | Gemini 3 Deep Think | 192K | 64K | Yes |
| `subscription-bridge-gemini-pro` | Gemini 3.1 Pro | 1M | 64K | Yes |
| `subscription-bridge-chatgpt` | ChatGPT (GPT-4o) | 128K | 16K | Yes |

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
