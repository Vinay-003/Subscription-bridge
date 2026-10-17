#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8787}"
CDP_PORT="${2:-${BRIDGE_CDP_PORT:-9555}}"

stop_by_port() {
    local label="$1"
    local port="$2"
    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)

    if [ -z "$pids" ]; then
        echo "No $label found on port $port"
        return 0
    fi

    for PID in $pids; do
        echo "Sending SIGINT to $label PID $PID..."
        kill -INT "$PID" 2>/dev/null || true
    done

    sleep 2

    for PID in $pids; do
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force-killing $label PID $PID..."
            kill -9 "$PID" 2>/dev/null || true
        fi
    done

    echo "Stopped $label on port $port"
}

stop_by_port "bridge server" "$PORT"
stop_by_port "Chrome (CDP)" "$CDP_PORT"
pkill -f "remote-debugging-port=$CDP_PORT" 2>/dev/null || true
