#!/usr/bin/env bash
# Drop all tables, recreate the schema and load the demo data. Safe while the server runs.
source "$(dirname "$0")/_env.sh"
python -m app.seed.seed
