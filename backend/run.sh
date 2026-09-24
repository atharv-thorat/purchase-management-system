#!/usr/bin/env bash
# Start the API on http://localhost:8000 (docs at /docs). Seeds the database on first run.
# Usage: ./run.sh [--reset]    --reset wipes and reseeds the database first.
source "$(dirname "$0")/_env.sh"

if [ "${1:-}" = "--reset" ] || [ ! -f pms.db ]; then
  python -m app.seed.seed
fi

exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8000}"
