#!/usr/bin/env bash
# Start the API on http://localhost:8000 (docs at /docs). Seeds an empty database on first run.
# Usage: ./run.sh [--reset]    --reset wipes and reseeds the demo data first.
# Env: PORT (default 8000), PMS_DATABASE_URL, PMS_CORS_ORIGINS — see app/core/config.py.
source "$(dirname "$0")/_env.sh"

if [ "${1:-}" = "--reset" ]; then
  python -m app.seed.seed
else
  python -m app.seed.seed --if-empty
fi

exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8000}"
