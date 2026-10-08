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

# Stream the sources into the container instead of bind-mounting the repo:
# works on Docker Desktop without file-sharing access to the checkout (e.g.
# ~/Documents on macOS) and on remote/rootless daemons. COPYFILE_DISABLE and
# --no-mac-metadata stop macOS bsdtar from adding AppleDouble ._* files.
TAR_FLAGS=(--exclude='__pycache__' --exclude='.pytest_cache' --exclude='._*')
if tar --version 2>/dev/null | grep -q bsdtar; then
  TAR_FLAGS+=(--no-xattrs --no-mac-metadata)
fi
COPYFILE_DISABLE=1 tar -C "$ROOT" "${TAR_FLAGS[@]}" -cf - backend database/init | \
docker run -i --rm --network "$NET" \
  -e TEST_DATABASE_URL="postgresql://sheetstorm:sheetstorm-test@${PG}:5432/sheetstorm_test" \
  -e TEST_REDIS_URL="redis://${REDIS}:6379/0" \
  -e DB_INIT_DIR=/tmp/src/database/init \
  --entrypoint sh "$IMAGE" -c \
  'mkdir -p /tmp/src && tar -xf - -C /tmp/src && cd /tmp/src/backend && exec python -m pytest "$@"' \
  sh "$@"
