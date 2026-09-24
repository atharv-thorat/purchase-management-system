# Shared by run.sh and reset_db.sh: create/refresh .venv and activate it.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY="${PYTHON:-python3}"
  "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || { echo "Python 3.11+ required (found $("$PY" --version)). Set PYTHON=/path/to/python3.x" >&2; exit 1; }
  echo "Creating virtualenv with $("$PY" --version)..."
  "$PY" -m venv .venv
fi

# Reinstall only when requirements.txt changes.
STAMP=.venv/.requirements.sha
SUM=$(shasum requirements.txt | cut -d' ' -f1)
if [ "$(cat "$STAMP" 2>/dev/null || true)" != "$SUM" ]; then
  echo "Installing dependencies..."
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  echo "$SUM" > "$STAMP"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
