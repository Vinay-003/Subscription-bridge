# SubscriptionBridge — Browser Setup

## Overview

SubscriptionBridge uses Playwright to automate browser-based LLM sessions. It supports two modes:

1. **Managed mode** — Playwright launches its own Chromium instance with a persistent profile
2. **CDP mode (recommended)** — You start Chrome manually, and SubscriptionBridge connects via Chrome DevTools Protocol

---

## CDP Mode (Recommended)

CDP mode lets you use your existing Chrome with a dedicated automation profile.

### Default CDP URL

```
http://127.0.0.1:9555
```

> Port 9555 is the default, set in `configs/app.yaml`. Override with `BRIDGE_CDP_URL`.

### Launch Command (Linux / Google Chrome)

```bash
google-chrome \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check \
  --disable-notifications \
  --disable-popup-blocking \
  --disable-session-crashed-bubble \
  --disable-sync \
  --start-maximized
```

### Other Platforms

**Linux (Chromium):**
```bash
chromium \
  --remote-debugging-port=9555 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check
```

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9555 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check
```

**Windows PowerShell:**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9555 `
  --user-data-dir="$env:USERPROFILE\.subscription-bridge\chrome-profile" `
  --no-first-run `
  --no-default-browser-check
```

### Start the Bridge Server

With Chrome running, start the bridge server in a separate terminal:

```bash
BRIDGE_CDP_URL=http://127.0.0.1:9555 bridge server --host 127.0.0.1 --port 8787 --provider both
```

Or use the all-in-one script:

```bash
./start.sh both
```

### Verify CDP Connection

```bash
bridge browser doctor
```

This checks:
- Whether `browser.cdp_url` from config is reachable
- Whether selector YAML files can be loaded
- Whether debug directories exist

---

## Managed Mode (Alternative)

In managed mode, Playwright handles everything. Use default config:

```yaml
browser:
  mode: managed
  headless: false
```

SubscriptionBridge will launch Chromium automatically with a fresh profile at `~/.subscription-bridge/chrome-profile`.

To use Google Chrome instead of the Playwright Chromium bundle, set `BRIDGE_CHROME_PATH`:

```bash
export BRIDGE_CHROME_PATH=/usr/bin/google-chrome
```

---

## Provider Login

After launching Chrome in CDP mode:

**Gemini:**
1. Navigate to `https://gemini.google.com/app`
2. Log in with your Google account
3. Leave the browser window open

**ChatGPT:**
1. Navigate to `https://chatgpt.com`
2. Log in with your OpenAI account
3. Leave the browser window open

You only need to log in once. The profile at `~/.subscription-bridge/chrome-profile` is persistent.

Verify:
```bash
bridge provider health gemini
bridge provider health chatgpt
```

---

## Safety Rules

- **Use a dedicated automation profile.** Do not use your main daily Chrome profile.
- **Never log cookies, tokens, or browser storage.** SubscriptionBridge has built-in redaction.
- **If Chrome is already open with the same profile**, remote debugging flags may not apply. Close all Chrome instances first.
- **Port 9555 is configurable.** Override with `BRIDGE_CDP_URL` or `browser.cdp_url` in `configs/app.yaml`.
- **Do not bypass paywalls, captchas, or anti-bot systems.** This is a personal local automation project.
