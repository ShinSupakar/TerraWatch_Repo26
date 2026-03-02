#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

mkdir -p .run

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "[setup] creating Python virtualenv..."
  python3 -m venv .venv
fi

port_pid() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

if [[ ! -d frontend/node_modules ]]; then
  echo "[setup] frontend dependencies missing. Run: cd frontend && npm install"
fi

backend_port_pid="$(port_pid 8000)"
if [[ -n "${backend_port_pid}" ]]; then
  echo "[skip] backend port 8000 already in use (pid ${backend_port_pid})"
  echo "${backend_port_pid}" > .run/backend.pid
elif [[ ! -f .run/backend.pid ]] || ! kill -0 "$(cat .run/backend.pid)" >/dev/null 2>&1; then
  echo "[start] backend on http://127.0.0.1:8000"
  nohup ./.venv/bin/python -m uvicorn backend:app --host 127.0.0.1 --port 8000 > .run/backend.log 2>&1 &
  echo $! > .run/backend.pid
else
  echo "[skip] backend already running (pid $(cat .run/backend.pid))"
fi

frontend_port_pid="$(port_pid 5173)"
if [[ -n "${frontend_port_pid}" ]]; then
  echo "[skip] frontend port 5173 already in use (pid ${frontend_port_pid})"
  echo "${frontend_port_pid}" > .run/frontend.pid
elif [[ ! -f .run/frontend.pid ]] || ! kill -0 "$(cat .run/frontend.pid)" >/dev/null 2>&1; then
  echo "[start] frontend on http://127.0.0.1:5173"
  nohup npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 > .run/frontend.log 2>&1 &
  echo $! > .run/frontend.pid
else
  echo "[skip] frontend already running (pid $(cat .run/frontend.pid))"
fi

echo
echo "Started. Logs:"
echo "  tail -f .run/backend.log"
echo "  tail -f .run/frontend.log"
echo
echo "Stop services with: ./stop_all.sh"
