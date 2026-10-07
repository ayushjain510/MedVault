#!/bin/sh
# Seed the database on first boot, then serve.
# Idempotent: an existing database is left untouched, so restarts and mounted
# volumes keep their data.
set -e

DB="/app/database/sepsis_ai.db"

if [ ! -f "$DB" ]; then
  echo "[entrypoint] No database found at $DB — seeding from trained models…"
  python seed.py
  echo "[entrypoint] Seed complete."
else
  echo "[entrypoint] Existing database found — skipping seed."
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
