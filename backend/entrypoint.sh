#!/bin/bash
set -euo pipefail

# Apply database migrations on startup so a bare `docker compose up` yields a
# working schema. A failed migration is FATAL: the container exits non-zero so
# the problem is visible (restart loop / unhealthy) instead of the API running
# against a half-migrated schema. The DB may still be accepting connections
# for a few seconds after its healthcheck passes, so retry with backoff first.
# Use the app factory, not wsgi.py: wsgi.py calls eventlet.monkey_patch(),
# which (after the flask CLI has already imported Flask/werkzeug) logs
# spurious "Working outside of application context" tracebacks.
export FLASK_APP="${FLASK_APP:-app:create_app}"

MAX_ATTEMPTS="${MIGRATION_MAX_ATTEMPTS:-5}"
attempt=1
delay=2
until flask db upgrade; do
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
        echo "[entrypoint] ERROR: 'flask db upgrade' failed after ${attempt} attempts; refusing to start." >&2
        exit 1
    fi
    echo "[entrypoint] 'flask db upgrade' failed (attempt ${attempt}/${MAX_ATTEMPTS}); retrying in ${delay}s..." >&2
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
done
echo "[entrypoint] Database migrations applied."

exec "$@"
