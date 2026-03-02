#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

for svc in backend frontend; do
  pid_file=".run/${svc}.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "[stop] $svc (pid $pid)"
      kill "$pid" || true
    else
      echo "[skip] $svc pid file exists but process not running"
    fi
    rm -f "$pid_file"
  else
    echo "[skip] $svc not running"
  fi
done
