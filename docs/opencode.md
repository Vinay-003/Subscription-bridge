# SubscriptionBridge — OpenCode Integration

## Overview

SubscriptionBridge exposes an OpenAI-compatible API at `/v1` so that
[OpenCode](https://opencode.ai) and other OpenAI-compatible clients can use
browser-based LLMs (Gemini) through SubscriptionBridge.

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
          "name": "Gemini 2.0 Flash",
          "limit": { "context": 100000, "output": 8192 }
        },
        "subscription-bridge-gemini-thinking": {
          "name": "Gemini 2.5 Pro (thinking)",
          "limit": { "context": 500000, "output": 65536 }
        },
        "subscription-bridge-gemini-pro": {
          "name": "Gemini 2.5 Pro",
          "limit": { "context": 900000, "output": 65536 }
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
uses a fresh Gemini chat or guaranteed reset. OpenCode is the source of truth.

---

## Subagent Model Mapping

OpenCode can use different models for different agent types.
Recommended configuration:

| Agent Role  | Recommended Model                   |
|-------------|--------------------------------------|
| `build`     | `subscription-bridge-gemini-pro`     |
| `plan`      | `subscription-bridge-gemini-thinking` |
| `explore`   | `subscription-bridge-gemini-fast`    |
| `review`    | `subscription-bridge-gemini-pro`     |

SubscriptionBridge does not implement subagents. OpenCode manages agents.

---

## Setup Steps

```bash
# 1. Start the SubscriptionBridge server
bridge server --host 127.0.0.1 --port 8787

# 2. Verify models
curl http://127.0.0.1:8787/v1/models

# 3. Test with fake provider
curl -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "subscription-bridge-fake",
    "messages": [{"role": "user", "content": "Say hello"}]
  }'

# 4. For Gemini models, start Chrome with remote debugging
google-chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check

# 5. Navigate to https://gemini.google.com/app and log in manually
# 6. Select the model in OpenCode
```

---

## Model Reference

| Model ID | Gemini Variant | Context | Chrome Required |
|----------|---------------|---------|-----------------|
| `subscription-bridge-fake` | Deterministic test | 32K | No |
| `subscription-bridge-gemini-fast` | 2.0 Flash | 100K | Yes |
| `subscription-bridge-gemini-thinking` | 2.5 Pro (thinking) | 500K | Yes |
| `subscription-bridge-gemini-pro` | 2.5 Pro | 900K | Yes |

---

## Tool-Call Compatibility

SubscriptionBridge supports OpenAI tool calls in the following way:

1. **Tools are accepted** in `/v1/chat/completions` requests
2. **Tools are converted** into Gemini prompt instructions — the model is told
   to respond with a JSON `tool_calls` object when a tool is needed
3. **Gemini's JSON output is parsed** and converted to OpenAI-compatible
   `tool_calls` in the response
4. **Tool results** from OpenCode (`role: "tool"`) are converted into readable
   transcript entries in the prompt
5. **SubscriptionBridge does not execute** tools — OpenCode handles execution

When Gemini decides to call a tool, the response contains:
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

- **Tool call reliability**: Gemini web UI may not reliably produce structured
  tool call JSON. Results may vary compared to API-based models.
- **Streaming is simulated**: True token-by-token streaming from the browser
  provider is not available. Response text is chunked into SSE events.
- **Token counts are approximate**: Uses character count / 4, not a real tokenizer.
- **Context limit is approximate**: Based on estimated tokens. If exceeded, the
  API returns `context_length_exceeded` — OpenCode compaction handles this.
- **Browser latency**: Gemini responses are slower than API-based models.
- **No multimodal**: Image inputs in content arrays are accepted but ignored.
- **API key**: Any value works (e.g., `"dummy"`). The server does not validate.
