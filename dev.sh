#!/usr/bin/env bash
# One command for the demo: FastAPI on :8000 and Next.js on :3000. Ctrl-C stops both.
#
#   ./dev.sh            start (installs dependencies and seeds the database on first run)
#   ./dev.sh --reset    restore the exact demo starting data, then start. Also works while the
#                       app is already running (e.g. from a second terminal mid-demo).
#
# Ports can be moved with PMS_BACKEND_PORT / PMS_FRONTEND_PORT (e.g. to run a second copy).
# After the first run no network is needed: installs are skipped and fonts/docs are local.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${PMS_BACKEND_PORT:-8000}"
FRONTEND_PORT="${PMS_FRONTEND_PORT:-3000}"
RESET="${1:-}"
PIDS=()

# Point the two halves at each other on whatever ports are in use.
export PORT="$BACKEND_PORT"
export PMS_CORS_ORIGINS="[\"http://localhost:$FRONTEND_PORT\",\"http://127.0.0.1:$FRONTEND_PORT\"]"
export NEXT_PUBLIC_API_URL="http://localhost:$BACKEND_PORT/api"
export NEXT_TELEMETRY_DISABLED=1

in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
backend_ok() { curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; }
frontend_ok() { curl -sf -o /dev/null "http://localhost:$FRONTEND_PORT/login" 2>/dev/null; }

cleanup() {
  trap - INT TERM EXIT
  if [ ${#PIDS[@]} -gt 0 ]; then
    echo; echo "Stopping…"
    for pid in "${PIDS[@]}"; do pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

command -v node >/dev/null || { echo "Node.js 18.17+ is required for the frontend (https://nodejs.org)." >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>18||(a===18&&b>=17)?0:1)' \
  || { echo "Node.js 18.17+ is required (found $(node --version))." >&2; exit 1; }

# ---- backend ------------------------------------------------------------------------------------
if in_use "$BACKEND_PORT"; then
  backend_ok || { echo "Port $BACKEND_PORT is taken by another program. Free it or set PMS_BACKEND_PORT." >&2; exit 1; }
  echo "▶ Backend already running on :$BACKEND_PORT — using it."
  if [ "$RESET" = "--reset" ]; then "$ROOT/backend/reset_db.sh" >/dev/null && echo "▶ Demo data restored."; fi
else
  echo "▶ Backend: starting on http://localhost:$BACKEND_PORT (API docs at /docs)"
  "$ROOT/backend/run.sh" $RESET &
  PIDS+=($!)
fi

# ---- frontend -----------------------------------------------------------------------------------
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "▶ Frontend: installing dependencies (first run)…"
  npm install --no-fund --no-audit
fi
if in_use "$FRONTEND_PORT"; then
  frontend_ok || { echo "Port $FRONTEND_PORT is taken by another program. Free it or set PMS_FRONTEND_PORT." >&2; exit 1; }
  echo "▶ Frontend already running on :$FRONTEND_PORT — using it."
else
  echo "▶ Frontend: starting on http://localhost:$FRONTEND_PORT"
  npx next dev -p "$FRONTEND_PORT" &
  PIDS+=($!)
fi

# ---- ready --------------------------------------------------------------------------------------
for _ in $(seq 1 120); do
  if backend_ok && frontend_ok; then
    echo; echo "✔ Ready: open http://localhost:$FRONTEND_PORT  (every demo user's password: demo123)"
    break
  fi
  sleep 1
done
backend_ok && frontend_ok || { echo "Something didn't start — see the output above." >&2; exit 1; }

if [ ${#PIDS[@]} -gt 0 ]; then wait; fi
