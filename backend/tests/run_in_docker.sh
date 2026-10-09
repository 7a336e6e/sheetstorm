#!/usr/bin/env bash
# Run the backend test suite in Docker against throwaway Postgres + Redis.
#
#   backend/tests/run_in_docker.sh                 # whole suite
#   backend/tests/run_in_docker.sh -k custody -x   # extra args go to pytest
#
# Everything (network, containers, the default image tag) is named with a
# per-run id and removed on exit, including on Ctrl-C/TERM, so any number of
# runs (worktrees, CI jobs) can execute concurrently; nothing touches the
# docker compose stack, its volumes, or host ports. The test database is
# rebuilt from database/init/*.sql and the full Alembic chain on every run
# (this also exercises the fresh-install path).
#
# Env overrides:
#   TEST_RUN_ID   run id used in every resource name (default: random);
#                 [a-z0-9_.-] only. Resources: sheetstorm-test-<id>-{net,pg,redis,pytest}
#   IMAGE         test image tag. Default sheetstorm-backend-test-<id>, untagged
#                 on exit (layers stay in the build cache, so rebuilds are fast).
#                 An explicit IMAGE (e.g. sheetstorm-backend-test-<wp-id>) is kept.
#   SHEETSTORM_ROOT (repo root), PG_IMAGE (default postgres:16-alpine),
#   KEEP=1 (keep containers/network/image for debugging).
set -euo pipefail

ROOT="${SHEETSTORM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN_ID="${TEST_RUN_ID:-$(date +%s)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')}"
if ! [[ "$RUN_ID" =~ ^[a-z0-9][a-z0-9_.-]{0,40}$ ]]; then
  echo "run_in_docker.sh: TEST_RUN_ID must match [a-z0-9][a-z0-9_.-]{0,40}" >&2
  exit 2
fi
NET="sheetstorm-test-${RUN_ID}-net"
PG="sheetstorm-test-${RUN_ID}-pg"
REDIS="sheetstorm-test-${RUN_ID}-redis"
RUNNER="sheetstorm-test-${RUN_ID}-pytest"
LABEL="sheetstorm.test-run=${RUN_ID}"
if [ -n "${IMAGE:-}" ]; then
  OWN_IMAGE=0
else
  IMAGE="sheetstorm-backend-test-${RUN_ID}"
  OWN_IMAGE=1
fi
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if [ "${KEEP:-0}" != "1" ]; then
    docker rm -f "$RUNNER" "$PG" "$REDIS" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    if [ "$OWN_IMAGE" = "1" ]; then
      docker image rm "$IMAGE" >/dev/null 2>&1 || true
    fi
  else
    echo "KEEP=1: left $RUNNER $PG $REDIS, network $NET, image $IMAGE" >&2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

echo "run_in_docker.sh: run id ${RUN_ID}" >&2
# Run by image ID, not tag: a concurrent build retagging $IMAGE cannot swap
# the image under this run.
IMAGE_ID="$(docker build -q --target test -t "$IMAGE" "$ROOT/backend")"
docker network create --label "$LABEL" "$NET" >/dev/null
docker run -d --name "$PG" --label "$LABEL" --network "$NET" \
  -e POSTGRES_USER=sheetstorm -e POSTGRES_PASSWORD=sheetstorm-test -e POSTGRES_DB=sheetstorm_test \
  "$PG_IMAGE" >/dev/null
docker run -d --name "$REDIS" --label "$LABEL" --network "$NET" redis:7-alpine >/dev/null

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
docker run -i --rm --name "$RUNNER" --label "$LABEL" --network "$NET" \
  -e TEST_DATABASE_URL="postgresql://sheetstorm:sheetstorm-test@${PG}:5432/sheetstorm_test" \
  -e TEST_REDIS_URL="redis://${REDIS}:6379/0" \
  -e DB_INIT_DIR=/tmp/src/database/init \
  --entrypoint sh "$IMAGE_ID" -c \
  'mkdir -p /tmp/src && tar -xf - -C /tmp/src && cd /tmp/src/backend && exec python -m pytest "$@"' \
  sh "$@" &
# Wait in the background so a TERM/HUP sent to this script runs the cleanup
# trap immediately (bash defers traps while a foreground command runs).
wait $!
