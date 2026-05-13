# SubscriptionBridge — Configuration Reference

## Overview

Configuration is loaded from `configs/app.yaml` with environment variable overrides.
A `.env` file in the project root is also loaded automatically.

---

## `configs/app.yaml`

### App section

```yaml
app:
  name: SubscriptionBridge
  version: "0.1.0"
  default_provider: fake
  max_steps: 25
  default_timeout_seconds: 300
  data_dir: ~/.subscription-bridge
  log_dir: ~/.subscription-bridge/logs
  index_dir: ~/.subscription-bridge/index
```

| Key | Default | Description |
|-----|---------|-------------|
| `default_provider` | `fake` | Provider used when none is specified |
| `max_steps` | `25` | Default max agent loop iterations |
| `default_timeout_seconds` | `300` | Default timeout for provider requests |

### Browser section

```yaml
browser:
  mode: managed
  cdp_url: "http://127.0.0.1:9333"
  headless: false
  user_data_dir: "~/.subscription-bridge/chrome-profile"
  downloads_dir: "~/.subscription-bridge/downloads"
  debug_dir: "~/.subscription-bridge/debug"
  max_sessions: 3
  session_ttl_seconds: 600
  download_timeout_seconds: 180
```

| Key | Default | Description |
|-----|---------|-------------|
| `mode` | `managed` | `managed` (Playwright launches browser) or `cdp` (connect to existing Chrome) |
| `cdp_url` | `http://127.0.0.1:9333` | CDP endpoint for `cdp` mode |
| `headless` | `false` | Run browser in headless mode |
| `user_data_dir` | `~/.subscription-bridge/chrome-profile` | Browser profile directory |
| `max_sessions` | `3` | Maximum concurrent browser tab sessions |
| `session_ttl_seconds` | `600` | Idle session time-to-live |

**Environment overrides**: `BRIDGE_BROWSER_MODE`, `BRIDGE_CDP_URL`, `BRIDGE_HEADLESS`

### Memory section

```yaml
memory:
  index_dir_name: ".subscription_bridge/index"
  embedding_provider: "hash"
  embedding_dim: 384
  chunk_max_lines: 160
  chunk_overlap_lines: 20
  max_file_bytes: 500000
```

| Key | Default | Description |
|-----|---------|-------------|
| `embedding_provider` | `hash` | `hash` (deterministic) or `sentence_transformer` |
| `chunk_max_lines` | `160` | Maximum lines per chunk |
| `chunk_overlap_lines` | `20` | Overlap lines between adjacent chunks |
| `max_file_bytes` | `500000` | Maximum file size for indexing |

### Gemini uploads section

```yaml
gemini:
  uploads:
    enabled: true
    max_files: 10
    max_file_bytes: 25000000
    upload_timeout_seconds: 180
    allow_unknown_extensions: true
    block_archives: false
    block_empty_files: false
    block_hidden_files: false
    block_sensitive_files: true
    allow_paths_outside_workspace: true
```

| Key | Default | Description |
|-----|---------|-------------|
| `max_files` | `10` | Maximum files per upload |
| `max_file_bytes` | `25000000` | Maximum file size (25MB) |
| `allow_unknown_extensions` | `true` | Allow files with unrecognized extensions |
| `block_sensitive_files` | `true` | Block `.env`, `.ssh/`, `id_rsa`, etc. |
| `block_archives` | `false` | Block `.zip`, `.tar.gz`, etc. |
| `block_empty_files` | `false` | Block 0-byte files |
| `block_hidden_files` | `false` | Block files starting with `.` |

---

## `configs/providers.yaml`

Defines providers, their capabilities, and routing rules:

```yaml
providers:
  fake:
    enabled: true
    capabilities: [text_chat, code_reasoning]
    priority: 0

  gemini:
    enabled: true
    capabilities: [text_chat, code_reasoning, file_upload, vision]
    url: "https://gemini.google.com/app"
    priority: 10
```

Routing rules automatically route tasks containing keywords like "architecture" or "design" to specific providers.

---

## `configs/selectors/gemini.yaml`

Centralized CSS selectors for the Gemini web UI. Organized by interaction type:

- `composer` — Prompt input element
- `response` — Assistant response elements
- `progress` — Loading/thinking indicators
- `upload_inputs` — File input elements
- `attach_buttons` — Attachment/upload buttons
- `attachment_previews` — Uploaded file previews
- `buttons` — Send, new chat buttons
- `unsafe_click_words` — Labels to never click (delete, settings, etc.)

---

## `configs/tool_permissions.yaml`

Defines tool-level safety policies:

```yaml
bash:
  enabled: true
  timeout_seconds: 120
  deny_commands:
    - "rm -rf /"
    - "sudo"
    - "shutdown"
    - "reboot"
    - "mkfs"
    - "fdisk"
    - "dd if="
    - "passwd"
```

Deny patterns are checked before any command executes.

---

## Environment Variables

| Variable | Overrides |
|----------|-----------|
| `BRIDGE_DEFAULT_PROVIDER` | `app.default_provider` |
| `BRIDGE_LOG_LEVEL` | `logging.level` |
| `BRIDGE_LOG_FORMAT` | `logging.format` |
| `BRIDGE_BROWSER_MODE` | `browser.mode` |
| `BRIDGE_CDP_URL` | `browser.cdp_url` |
| `BRIDGE_HEADLESS` | `browser.headless` |

A `.env` file in the project root is loaded automatically via `python-dotenv`.
