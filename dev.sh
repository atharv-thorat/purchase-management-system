#!/usr/bin/env bash
# Start the whole app for a demo: FastAPI on :8000 and Next.js on :3000. Ctrl-C stops both.
#   ./dev.sh            start (seeds the database on first run)
#   ./dev.sh --reset    wipe and reseed the demo data first
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS=()

in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

cleanup() {
  trap - INT TERM EXIT
  echo; echo "Stopping…"
  for pid in "${PIDS[@]}"; do pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Backend
if in_use 8000; then
  echo "▶ Backend: something is already listening on :8000 — using it."
  [ "${1:-}" = "--reset" ] && "$ROOT/backend/reset_db.sh"
else
  echo "▶ Backend: starting on http://localhost:8000 (API docs at /docs)"
  "$ROOT/backend/run.sh" ${1:-} &
  PIDS+=($!)
fi

# Frontend
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "▶ Frontend: installing dependencies (first run)…"
  npm install --no-fund --no-audit
fi
if in_use 3000; then
  echo "▶ Frontend: something is already listening on :3000 — using it."
else
  echo "▶ Frontend: starting on http://localhost:3000"
  npm run dev &
  PIDS+=($!)
fi

# Wait until both answer, then say where to go.
for _ in $(seq 1 90); do
  if curl -sf http://localhost:8000/api/health >/dev/null && curl -sf -o /dev/null http://localhost:3000/login; then
    echo; echo "✔ Ready: open http://localhost:3000  (demo password: demo123)"; break
  fi
  sleep 1
done

if [ ${#PIDS[@]} -gt 0 ]; then wait; fi
