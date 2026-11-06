#!/bin/sh
set -e
# Run migrations with the owner role (AXIOM_MIGRATION_DATABASE_URL), serve with the RLS-bound app role.
if [ -n "$AXIOM_MIGRATION_DATABASE_URL" ] || echo "$AXIOM_DATABASE_URL" | grep -q '^postgresql'; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' "$@"
