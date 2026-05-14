#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
BRIDGE="$SCRIPT_DIR/.venv/bin/bridge"
CHROME_PROFILE="$HOME/.subscription-bridge/chrome-profile"
CDP_PORT=9333
API_PORT=8787
BRIDGE_PID=""

cleanup() {
    echo ""
    echo "=== Shutting down ==="
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null && echo "Stopped bridge server (PID $BRIDGE_PID)"
    echo "Chrome CDP tab left open (close manually)"
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
    sleep 1
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

# ---- 5. Launch bridge API server ----
echo "[4] Starting bridge API server on port $API_PORT..."
$BRIDGE server --host 127.0.0.1 --port $API_PORT &
BRIDGE_PID=$!

# ---- 6. Wait for API server to be ready ----
echo "[5] Waiting for API server..."
for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:$API_PORT/health > /dev/null 2>&1; then
        echo "     API ready after ${i}s"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "ERROR: API server did not start within 15s"
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
echo "============================================"
echo ""
echo "OpenCode desktop is already configured to use this endpoint."
echo "Press Ctrl+C to shut everything down."
echo ""

# Keep running until Ctrl+C
wait $BRIDGE_PID
