#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8787}"

echo "Looking for bridge server on port $PORT..."

PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo "No server found on port $PORT"
    exit 0
fi

for PID in $PIDS; do
    echo "Sending SIGINT to PID $PID for graceful shutdown..."
    kill -INT "$PID" 2>/dev/null || true
done

sleep 2

for PID in $PIDS; do
    if kill -0 "$PID" 2>/dev/null; then
        echo "Force-killing PID $PID..."
        kill -9 "$PID" 2>/dev/null || true
    fi
done

echo "Stopped server(s) on port $PORT"
