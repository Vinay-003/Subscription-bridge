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

OpenCode manages context and session history. Each request to SubscriptionBridge
uses a fresh chat or guaranteed reset. OpenCode is the source of truth.

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
# 1. Start Chrome with remote debugging
google-chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check

# 2. Navigate to https://gemini.google.com/app and log in manually

# 3. Start the bridge server
bridge server --provider gemini

# 4. Verify models
curl http://127.0.0.1:8787/v1/models

# 5. Select a Gemini model in OpenCode
```

### Option B: ChatGPT

```bash
# 1. Start Chrome with remote debugging
google-chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check

# 2. Navigate to https://chatgpt.com and log in manually

# 3. Start the bridge server
bridge server --provider chatgpt

# 4. Verify models
curl http://127.0.0.1:8787/v1/models

# 5. Select the ChatGPT model in OpenCode
```

### Option C: Both

```bash
# Start server with both providers
bridge server --provider both

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
2. **Tools are converted** into prompt instructions — the model is told
   to respond with a JSON `tool_calls` object when a tool is needed
3. **The model's JSON output is parsed** and converted to OpenAI-compatible
   `tool_calls` in the response
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

- **Tool call reliability**: Browser-based models may not reliably produce structured
  tool call JSON. Results may vary compared to API-based models.
- **Streaming is simulated**: True token-by-token streaming from the browser
  provider is not available. Response text is chunked into SSE events.
- **Token counts are approximate**: Uses character count / 4, not a real tokenizer.
- **Context limit is approximate**: Based on estimated tokens. If exceeded, the
  API returns `context_length_exceeded` — OpenCode compaction handles this.
- **Browser latency**: Responses are slower than API-based models.
- **No multimodal**: Image inputs in content arrays are accepted but ignored.
- **API key**: Any value works (e.g., `"dummy"`). The server does not validate.
