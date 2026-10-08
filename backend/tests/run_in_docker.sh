#!/usr/bin/env bash
# Run the backend test suite in Docker against throwaway Postgres + Redis.
#
#   backend/tests/run_in_docker.sh                 # whole suite
#   backend/tests/run_in_docker.sh -k custody -x   # extra args go to pytest
#
# Everything (network, containers) is created with a unique suffix and removed
# on exit; nothing touches the docker compose stack, its volumes, or host
# ports. The test database is rebuilt from database/init/*.sql and the full
# Alembic chain on every run (this also exercises the fresh-install path).
#
# Env overrides: SHEETSTORM_ROOT (repo root), IMAGE (test image tag),
#                PG_IMAGE (default postgres:16-alpine), KEEP=1 (keep containers).
set -euo pipefail

ROOT="${SHEETSTORM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SUFFIX="$(date +%s)-$$"
NET="sheetstorm-test-${SUFFIX}"
PG="sheetstorm-test-pg-${SUFFIX}"
REDIS="sheetstorm-test-redis-${SUFFIX}"
IMAGE="${IMAGE:-sheetstorm-backend-test}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"

cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    docker rm -f "$PG" "$REDIS" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

docker build -q --target test -t "$IMAGE" "$ROOT/backend" >/dev/null
docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" \
  -e POSTGRES_USER=sheetstorm -e POSTGRES_PASSWORD=sheetstorm-test -e POSTGRES_DB=sheetstorm_test \
  "$PG_IMAGE" >/dev/null
docker run -d --name "$REDIS" --network "$NET" redis:7-alpine >/dev/null

for _ in $(seq 1 60); do
  docker exec "$PG" pg_isready -U sheetstorm -d sheetstorm_test >/dev/null 2>&1 && break
  sleep 1
done
sleep 1

docker run --rm --network "$NET" \
  -v "$ROOT/backend:/app" \
  -v "$ROOT/database/init:/db-init:ro" \
  -w /app \
  -e TEST_DATABASE_URL="postgresql://sheetstorm:sheetstorm-test@${PG}:5432/sheetstorm_test" \
  -e TEST_REDIS_URL="redis://${REDIS}:6379/0" \
  -e DB_INIT_DIR=/db-init \
  --entrypoint python "$IMAGE" -m pytest "$@"
