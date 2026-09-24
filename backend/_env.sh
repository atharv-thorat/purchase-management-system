# Shared by run.sh and reset_db.sh: create/refresh .venv and activate it.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  # Use $PYTHON if given, else the newest python3.x on PATH that is 3.11+.
  PY="${PYTHON:-}"
  if [ -z "$PY" ]; then
    for candidate in python3.13 python3.12 python3.11 python3 python3.14; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        PY="$candidate"; break
      fi
    done
  fi
  [ -n "$PY" ] || { echo "Python 3.11+ is required. Install it, or set PYTHON=/path/to/python3.x" >&2; exit 1; }
  echo "Creating virtualenv with $("$PY" --version)..."
  "$PY" -m venv .venv
fi

# Reinstall only when requirements.txt changes (no network needed on later runs).
STAMP=.venv/.requirements.sum
SUM=$(cksum < requirements.txt | tr -d ' ')
if [ "$(cat "$STAMP" 2>/dev/null || true)" != "$SUM" ]; then
  echo "Installing backend dependencies..."
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  echo "$SUM" > "$STAMP"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
