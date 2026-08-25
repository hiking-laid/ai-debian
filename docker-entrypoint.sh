#!/bin/sh
# Container entrypoint: apply DB migrations (idempotent) then start the app.
# Alembic's `upgrade head` only applies migrations not yet recorded in alembic_version,
# so this is safe to run on every startup — empty DB gets created, current DB is a no-op.
set -e

echo "[entrypoint] applying database migrations..."
n=0
until toddler-dinner db upgrade; do
  n=$((n + 1))
  if [ "$n" -ge 10 ]; then
    echo "[entrypoint] database not ready after $n attempts; giving up." >&2
    exit 1
  fi
  echo "[entrypoint] database not ready (attempt $n) — retrying in 3s..." >&2
  sleep 3
done
echo "[entrypoint] migrations applied."

# Initial deployment only: seed the inventory catalog from the seed file when it's empty.
echo "[entrypoint] seeding inventory catalog if empty..."
toddler-dinner inventory seed || echo "[entrypoint] inventory seed skipped." >&2

exec "$@"
