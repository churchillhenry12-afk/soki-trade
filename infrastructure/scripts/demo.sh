#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "Soki Trade dependencies are missing. Run: make setup"
  exit 1
fi

if [[ ! -d apps/terminal-ui/node_modules ]]; then
  echo "Soki Trade frontend dependencies are missing. Run: make setup"
  exit 1
fi

export PYTHONPATH="packages/shared/src:apps/api/src"
export QFORGE_DEMO_MODE="true"

cleanup() {
  kill "${api_pid:-0}" "${ui_pid:-0}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run uvicorn qforge_api.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
npm run dev --prefix apps/terminal-ui &
ui_pid=$!

echo ""
echo "Soki Trade explicit mock research stack"
echo "Frontend: http://127.0.0.1:5173"
echo "API:      http://127.0.0.1:8000"
echo "OpenAPI:  http://127.0.0.1:8000/docs"
echo "Worker:   in-process demo orchestrator (Redis/Celery not required)"
echo "Mocks:    Hermes, MT5 read-only status, quantum QUBO backend, market data"
echo "Live:     disabled"
echo ""

wait -n "$api_pid" "$ui_pid"
