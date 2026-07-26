#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "Soki Trade dependencies are missing. Run: make setup"
  exit 1
fi

api_started="false"
api_pid=""

cleanup() {
  if [[ "$api_started" == "true" && -n "$api_pid" ]]; then
    kill "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  export PYTHONPATH="packages/shared/src:apps/api/src"
  export QFORGE_DEMO_MODE="false"
  uv run uvicorn qforge_api.main:app --host 127.0.0.1 --port 8000 >/tmp/qforge-api.log 2>&1 &
  api_pid=$!
  api_started="true"

  for _ in {1..40}; do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done

  if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "Soki Trade API failed to start. Inspect /tmp/qforge-api.log"
    exit 1
  fi
fi

echo "Starting Soki Trade"
echo "One terminal · one agent conversation · /setup for connections · /help for commands"
echo "Real candles download automatically. Live execution remains disabled."
sleep 0.4

export PYTHONPATH="packages/shared/src:apps/terminal-tui/src"
uv run python -m qforge_tui.main
