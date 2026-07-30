#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "soki code dependencies are missing. Run: make setup"
  exit 1
fi

if [[ ! -d apps/soki-code-web/node_modules ]]; then
  echo "soki code desktop dependencies are missing. Run: make setup"
  exit 1
fi

export PYTHONPATH="packages/shared/src:apps/api/src"
export QFORGE_DEMO_MODE="false"

api_pid=""
ui_pid=""
api_reused="false"
ui_reused="false"

port_is_open() {
  nc -z 127.0.0.1 "$1" >/dev/null 2>&1
}

next_free_port() {
  local candidate="$1"
  while port_is_open "$candidate"; do
    candidate=$((candidate + 1))
  done
  echo "$candidate"
}

is_soki_api() {
  curl -fsS "http://127.0.0.1:$1/health" 2>/dev/null \
    | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
}

is_soki_web() {
  curl -fsS "http://127.0.0.1:$1/" 2>/dev/null \
    | grep -Fq "<title>soki code</title>"
}

cleanup() {
  [[ -z "$ui_pid" ]] || kill "$ui_pid" 2>/dev/null || true
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

api_port=8000
if is_soki_api "$api_port"; then
  api_reused="true"
elif port_is_open "$api_port"; then
  api_port="$(next_free_port 8001)"
fi

if [[ "$api_reused" == "false" ]]; then
  uv run uvicorn qforge_api.main:app --host 127.0.0.1 --port "$api_port" &
  api_pid=$!
  for _ in {1..200}; do
    is_soki_api "$api_port" && break
    sleep 0.1
  done
  if ! is_soki_api "$api_port"; then
    echo "soki code API did not start on port $api_port."
    exit 1
  fi
fi

ui_port=5173
if [[ "$api_port" == "8000" ]] && is_soki_web "$ui_port"; then
  ui_reused="true"
elif port_is_open "$ui_port"; then
  ui_port="$(next_free_port 5174)"
fi

if [[ "$ui_reused" == "false" ]]; then
  VITE_API_URL="http://127.0.0.1:$api_port" \
    npm run dev --prefix apps/soki-code-web -- --port "$ui_port" &
  ui_pid=$!
  for _ in {1..120}; do
    is_soki_web "$ui_port" && break
    sleep 0.1
  done
  if ! is_soki_web "$ui_port"; then
    echo "soki code web app did not start on port $ui_port."
    exit 1
  fi
fi

desktop_url="http://127.0.0.1:$ui_port"
if [[ "$(uname -s)" == "Darwin" ]]; then
  open "$desktop_url"
fi

echo "  web      $desktop_url$([[ "$ui_reused" == "true" ]] && echo "  (already running)")"
echo "  api      http://127.0.0.1:$api_port$([[ "$api_reused" == "true" ]] && echo "  (already running)")"
echo "  mode     research + paper only"
echo ""

if [[ -z "$api_pid" && -z "$ui_pid" ]]; then
  echo "  soki code was already running, so no second process was started."
  exit 0
fi

echo "  Keep this terminal open. Press Ctrl+C to stop the processes started here."
echo ""

if [[ -n "$api_pid" && -n "$ui_pid" ]]; then
  wait -n "$api_pid" "$ui_pid"
elif [[ -n "$api_pid" ]]; then
  wait "$api_pid"
else
  wait "$ui_pid"
fi
