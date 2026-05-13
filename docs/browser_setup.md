# SubscriptionBridge — Browser Setup

## Overview

SubscriptionBridge uses Playwright to automate browser-based LLM sessions. It supports two modes:

1. **Managed mode** — Playwright launches its own Chromium instance with a persistent profile
2. **CDP mode** — You start Chrome manually, and SubscriptionBridge connects via Chrome DevTools Protocol

---

## Managed Mode (Default)

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

## CDP Mode (Recommended for Development)

CDP mode lets you use your existing Chrome with a dedicated automation profile.

### Default CDP URL

```
http://127.0.0.1:9333
```

> Port 9333 is the default. Port 9222 is unavailable on this machine.

### Launch Commands

**Linux (Google Chrome):**
```bash
google-chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check
```

**Linux (Chromium):**
```bash
chromium \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check
```

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/.subscription-bridge/chrome-profile" \
  --no-first-run \
  --no-default-browser-check
```

**Windows PowerShell:**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9333 `
  --user-data-dir="$env:USERPROFILE\.subscription-bridge\chrome-profile" `
  --no-first-run `
  --no-default-browser-check
```

### Verify CDP connection

```bash
bridge browser doctor
```

This checks:
- Whether `browser.cdp_url` from config is reachable
- Whether selector YAML files can be loaded
- Whether debug directories exist

---

## Gemini Manual Login

After launching Chrome in CDP mode:

1. Navigate to `https://gemini.google.com/app`
2. Log in with your Gemini account
3. Leave the browser window open
4. Run `bridge provider health gemini` to verify

You only need to log in once. The profile is persistent.

---

## Safety Rules

- **Use a dedicated automation profile.** Do not use your main daily Chrome profile.
- **Never log cookies, tokens, or browser storage.** SubscriptionBridge has built-in redaction.
- **If Chrome is already open with the same profile**, remote debugging flags may not apply. Close all Chrome instances first.
- **Port 9333 is configurable.** Override with `BRIDGE_CDP_URL` or `browser.cdp_url`.
- **Do not bypass paywalls, captchas, or anti-bot systems.** This is a personal local automation project.
