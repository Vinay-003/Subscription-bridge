#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
BRIDGE="$SCRIPT_DIR/.venv/bin/bridge"
CHROME_PROFILE="$HOME/.subscription-bridge/chrome-profile"
CDP_PORT=9333
API_PORT=8787
BRIDGE_PID=""
PROVIDER="${1:-gemini}"

usage() {
    echo "Usage: $0 [gemini|chatgpt|both]"
    echo ""
    echo "  gemini   - Use Gemini (default)"
    echo "  chatgpt  - Use ChatGPT"
    echo "  both     - Use both providers"
    echo ""
    echo "First time? Log in to your provider in the Chrome window that opens."
    echo "Login persists in the profile at: $CHROME_PROFILE"
}

if [ "$PROVIDER" = "--help" ] || [ "$PROVIDER" = "-h" ]; then
    usage
    exit 0
fi

if [ "$PROVIDER" != "gemini" ] && [ "$PROVIDER" != "chatgpt" ] && [ "$PROVIDER" != "both" ]; then
    echo "Error: Unknown provider '$PROVIDER'"
    usage
    exit 1
fi

cleanup() {
    echo ""
    echo "=== Shutting down ==="
    if [ -n "$BRIDGE_PID" ]; then
        kill -INT "$BRIDGE_PID" 2>/dev/null && echo "Sent shutdown signal to bridge server (PID $BRIDGE_PID)"
        sleep 2
        kill -9 "$BRIDGE_PID" 2>/dev/null || true
    fi
    CDP_PID=$(lsof -ti tcp:$CDP_PORT 2>/dev/null || true)
    if [ -n "$CDP_PID" ]; then
        echo "Closing Chrome CDP (PID $CDP_PID)..."
        kill "$CDP_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$CDP_PID" 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "============================================"
echo " SubscriptionBridge — Full Stack Launcher"
echo "============================================"

# ---- 1. Ensure Chrome profile dir exists ----
mkdir -p "$CHROME_PROFILE"
mkdir -p "$HOME/.subscription-bridge/downloads"
mkdir -p "$HOME/.subscription-bridge/debug"

# ---- 2. Check / kill existing Chrome on CDP port ----
CDP_PID=$(lsof -ti tcp:$CDP_PORT 2>/dev/null || true)
if [ -n "$CDP_PID" ]; then
    echo "[1] Killing existing Chrome on port $CDP_PORT (PID $CDP_PID)..."
    kill "$CDP_PID" 2>/dev/null || true
    for i in $(seq 1 10); do
        if ! lsof -ti tcp:$CDP_PORT > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# ---- 3. Launch Chrome with CDP ----
echo "[2] Launching Chrome with CDP on port $CDP_PORT..."
google-chrome \
    --remote-debugging-port=$CDP_PORT \
    --user-data-dir="$CHROME_PROFILE" \
    --no-first-run \
    --no-default-browser-check \
    --disable-notifications \
    --disable-popup-blocking \
    --disable-session-crashed-bubble \
    --start-maximized \
    > /dev/null 2>&1 &
CHROME_PID=$!

# ---- 4. Wait for CDP to be ready ----
echo "[3] Waiting for CDP endpoint..."
for i in $(seq 1 15); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1',$CDP_PORT)); s.close()" 2>/dev/null; then
        echo "     CDP ready after ${i}s"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "ERROR: Chrome CDP did not start within 15s"
        exit 1
    fi
    sleep 1
done

# ---- 5. Kill any leftover process on API port ----
API_PID=$(lsof -ti tcp:$API_PORT 2>/dev/null || true)
if [ -n "$API_PID" ]; then
    echo "[4] Killing existing process on port $API_PORT (PID $API_PID)..."
    kill "$API_PID" 2>/dev/null || true
    for i in $(seq 1 10); do
        if ! lsof -ti tcp:$API_PORT > /dev/null 2>&1; then
            echo "     Port freed after ${i}s"
            break
        fi
        sleep 1
    done
fi

# ---- 6. Launch bridge API server ----
echo "[5] Starting bridge API server on port $API_PORT (provider: $PROVIDER)..."
$BRIDGE server --host 127.0.0.1 --port $API_PORT --provider "$PROVIDER" &
BRIDGE_PID=$!

# ---- 7. Wait for API server to be ready ----
echo "[6] Waiting for API server..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:$API_PORT/health > /dev/null 2>&1; then
        echo "     API ready after ${i}s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: API server did not start within 30s"
        exit 1
    fi
    sleep 1
done

echo ""
echo "============================================"
echo " All systems ready!"
echo "   Chrome CDP : http://127.0.0.1:$CDP_PORT"
echo "   Bridge API : http://127.0.0.1:$API_PORT"
echo "   OpenCode   : http://127.0.0.1:$API_PORT/v1"
echo "   Provider   : $PROVIDER"
echo "============================================"
echo ""
echo "FIRST TIME? In the Chrome window that opened:"
if [ "$PROVIDER" = "gemini" ] || [ "$PROVIDER" = "both" ]; then
    echo "  1. Go to https://gemini.google.com/app"
    echo "  2. Log in with your Google account"
fi
if [ "$PROVIDER" = "chatgpt" ] || [ "$PROVIDER" = "both" ]; then
    echo "  1. Go to https://chatgpt.com"
    echo "  2. Log in with your OpenAI account"
fi
echo ""
echo "Press Ctrl+C to shut everything down."
echo ""

# Keep running until Ctrl+C
wait $BRIDGE_PID
