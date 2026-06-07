# SubscriptionBridge — API Documentation

## Overview

The FastAPI server exposes SubscriptionBridge functionality over HTTP. Start it with:

```bash
bridge server --host 127.0.0.1 --port 8787
```

Interactive API docs are available at http://127.0.0.1:8787/docs.

SubscriptionBridge has two execution modes:

- `/v1/*` is an OpenAI-compatible model gateway. It forwards prompts to browser-backed models and never executes local tools.
- `/agent/runs` and legacy `/run` execute SubscriptionBridge's native local agent loop, including local tools such as file reads, writes, grep, bash, patch, and codebase search.

---

## Endpoints

### GET /health

Returns server status and provider health information.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "providers": {
    "fake": "ready",
    "gemini": "login_required"
  }
}
```

**Example:**
```bash
curl http://127.0.0.1:8787/health
```

---

### POST /ask

Send a prompt to a provider.

**Request:**
```json
{
  "provider": "fake",
  "prompt": "Say hello",
  "files": [],
  "timeout_seconds": 300
}
```

**Response:**
```json
{
  "success": true,
  "provider": "fake",
  "text": "Hello! I am SubscriptionBridge's fake provider...",
  "error": null,
  "artifacts": [],
  "metadata": {}
}
```

For Gemini provider with files, the metadata includes upload info:

```json
{
  "metadata": {
    "attachment_count": 2,
    "attachment_names": ["report.pdf", "notes.docx"],
    "attachment_categories": ["document", "document"],
    "total_attachment_bytes": 124567,
    "upload_duration_seconds": 1.23
  }
}
```

**Examples:**
```bash
# Ask fake provider
curl -X POST http://127.0.0.1:8787/ask \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","prompt":"Say hello"}'

# Ask Gemini with a file
curl -X POST http://127.0.0.1:8787/ask \
  -H "Content-Type: application/json" \
  -d '{"provider":"gemini","prompt":"Summarize this file","files":["examples/files/sample.txt"]}'
```

---

### POST /run

Run the full native agent loop on a task. This endpoint is retained for compatibility and delegates to the same service as `/agent/runs`.

**Request:**
```json
{
  "provider": "fake",
  "task": "Read pyproject.toml and summarize dependencies",
  "workspace": ".",
  "max_steps": 10
}
```

**Response:**
```json
{
  "success": true,
  "answer": "Summary of dependencies...",
  "run_id": "run-abc123def456",
  "steps": 2,
  "status": "completed",
  "error": null
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8787/run \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","task":"test task","workspace":".","max_steps":5}'
```

---

### POST /agent/runs

Run the native SubscriptionBridge agent loop on a task. This endpoint executes local tools through `ToolExecutor`, so provide the intended workspace explicitly.

**Request:**
```json
{
  "provider": "fake",
  "task": "Read pyproject.toml and summarize dependencies",
  "workspace": ".",
  "max_steps": 10
}
```

**Response:**
```json
{
  "success": true,
  "answer": "Summary of dependencies...",
  "run_id": "run-abc123def456",
  "steps": 2,
  "status": "completed",
  "error": null
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8787/agent/runs \
  -H "Content-Type: application/json" \
  -d '{"provider":"fake","task":"test task","workspace":".","max_steps":5}'
```

---

### GET /sessions

List active browser sessions.

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "tab-abc123...",
      "provider_name": "gemini",
      "state": "IDLE",
      "current_run_id": null,
      "created_at": 1234567890.0,
      "last_used_at": 1234567890.0,
      "age_seconds": 120.0,
      "idle_seconds": 60.0
    }
  ]
}
```

---

### POST /sessions/{session_id}/reset

Reset a browser session.

**Response:**
```json
{
  "status": "reset",
  "session_id": "tab-abc123..."
}
```

---

### POST /codebase/index

Index a workspace for codebase search.

**Request:**
```json
{
  "workspace": "."
}
```

**Response:**
```json
{
  "success": true,
  "file_count": 117,
  "chunk_count": 158,
  "symbol_count": 1548,
  "duration_seconds": 6.8,
  "index_path": "/path/to/.subscription_bridge/index",
  "error": null
}
```

---

### POST /codebase/search

Search an indexed codebase.

**Request:**
```json
{
  "workspace": ".",
  "query": "provider adapter",
  "top_k": 10
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "file_path": "src/subscription_bridge/providers/registry.py",
      "start_line": 1,
      "end_line": 76,
      "score": 0.85,
      "match_type": "keyword+semantic",
      "preview": "from subscription_bridge.providers.base import ProviderAdapter...",
      "symbols": ["ProviderRegistry", "register"]
    }
  ],
  "indexed": true,
  "error": null
}
```

---

### GET /codebase/stats

Get codebase index statistics.

**Query parameters:** `workspace` (default: `.`)

**Response:**
```json
{
  "success": true,
  "workspace_root": "/path/to/project",
  "indexed_at": 1234567890.0,
  "file_count": 117,
  "chunk_count": 158,
  "symbol_count": 1548,
  "embedding_provider": "hash",
  "embedding_dim": 384,
  "index_path": "/path/to/.subscription_bridge/index",
  "error": null
}
```

---

## OpenAI-Compatible Endpoints

SubscriptionBridge exposes OpenAI-compatible endpoints for integration with
[OpenCode](https://opencode.ai) and other OpenAI-compatible clients. These
endpoints are a model gateway, not the native agent runtime.

### GET /v1/models

Returns available models in OpenAI format.

**Example:**
```bash
curl http://127.0.0.1:8787/v1/models
```

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "subscription-bridge-fake",
      "object": "model",
      "created": 0,
      "owned_by": "subscription-bridge"
    },
    {
      "id": "subscription-bridge-gemini",
      "object": "model",
      "created": 0,
      "owned_by": "subscription-bridge"
    }
  ]
}
```

### POST /v1/chat/completions

Send a chat completion request in OpenAI format. This endpoint forwards the
request to the selected provider and returns model output. It does not execute
local tools, even when `tools` are present.

**Request:**
```json
{
  "model": "subscription-bridge-fake",
  "messages": [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Say hello"}
  ],
  "temperature": 0.2,
  "max_tokens": 1024,
  "stream": false
}
```

**Non-streaming response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "subscription-bridge-fake",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

**Streaming (SSE):**
```bash
curl -N -X POST http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "subscription-bridge-fake",
    "messages": [
      {"role": "user", "content": "Stream a short greeting"}
    ],
    "stream": true
  }'
```

**Streaming response:**
```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":123,"model":"subscription-bridge-fake","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":123,"model":"subscription-bridge-fake","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":123,"model":"subscription-bridge-fake","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### OpenCode Configuration

See [opencode.md](opencode.md) for OpenCode integration setup.

### Limitations

- Token counts are approximate (character count / 4)
- Streaming is simulated by chunking the final response text
- Tool call execution for `/v1/chat/completions` is handled by the client, not SubscriptionBridge
- Use `/agent/runs` or `/run` when you want SubscriptionBridge to execute local tools
- Image inputs in content arrays are accepted but ignored
