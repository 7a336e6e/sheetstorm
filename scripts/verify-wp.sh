#!/usr/bin/env bash
# Run the merge gates from .plans/_integration.md §6 for a work package.
#
#   scripts/verify-wp.sh                 # gates for what changed vs the base
#   scripts/verify-wp.sh --all           # every gate (backend, mcp, frontend)
#   scripts/verify-wp.sh --backend --frontend --mcp --e2e   # explicit selection
#
# Gates:
#   backend   backend/tests/run_in_docker.sh (full suite, real Postgres + Redis;
#             includes test_migrations.py, i.e. the single-Alembic-head check)
#   mcp       mcp-server and mcp-bridge pytest suites in throwaway, digest-pinned
#             python containers from their hash-locked requirements-dev.lock
#   frontend  npm ci --ignore-scripts --legacy-peer-deps, tsc --noEmit, lint,
#             jest --ci (TZ=UTC, deterministic time tests), next build
#   e2e       playwright --grep @smoke against an ALREADY-RUNNING stack
#             (E2E_BASE_URL; integrator only, never selected automatically)
#   deps      fails when package.json / requirements*.txt changed vs the base
#             (only W0-TH may add dependencies; ALLOW_DEPS=1 to acknowledge)
#
# Env: WP_ID (default: from the branch name), BASE (default: the merge-base of
# HEAD with origin/integration; falls back to the local integration branch,
# then main), ALLOW_DEPS=1. Docker resources are named
# sheetstorm-verify-<WP_ID>-<rand>-* and removed on exit; nothing touches the
# docker compose stack or publishes ports.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
WP_ID="${WP_ID:-$(printf '%s' "${BRANCH##*/}" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9_.-' '-')}"
WP_ID="${WP_ID:0:30}"
if [ -z "${BASE:-}" ]; then
  # The merge-base with the published integration branch: a WP cut from an
  # earlier wave (or the integration branch itself before its push) is then
  # compared only with what it adds, not with main.
  if git rev-parse --verify -q origin/integration >/dev/null; then
    BASE="$(git merge-base origin/integration HEAD)"
  elif git rev-parse --verify -q integration >/dev/null; then
    BASE=integration
  else
    BASE=main
  fi
fi
RUN_ID="${WP_ID}-$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')"
PY_IMAGE='python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258'

run_backend=0 run_mcp=0 run_frontend=0 run_e2e=0 explicit=0
for arg in "$@"; do
  case "$arg" in
    --all) run_backend=1 run_mcp=1 run_frontend=1 explicit=1 ;;
    --backend) run_backend=1 explicit=1 ;;
    --mcp) run_mcp=1 explicit=1 ;;
    --frontend) run_frontend=1 explicit=1 ;;
    --e2e) run_e2e=1 explicit=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Files changed vs the merge base, plus uncommitted and untracked changes.
changed="$( { git diff --name-only "$(git merge-base "$BASE" HEAD)" HEAD; git diff --name-only HEAD; \
              git ls-files --others --exclude-standard; } | sort -u)"
if [ "$explicit" = 0 ]; then
  grep -qE '^(backend|database)/' <<<"$changed" && run_backend=1
  grep -qE '^mcp-(server|bridge)/' <<<"$changed" && run_mcp=1
  grep -qE '^frontend/' <<<"$changed" && run_frontend=1
  # Backend changes can break the MCP contract tests and vice versa.
  [ "$run_backend" = 1 ] && grep -qE '^backend/app/api/' <<<"$changed" && run_mcp=1
fi

containers=()
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  [ "${#containers[@]}" -gt 0 ] && docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

results=()
gate() {  # gate <name> <command...>
  local name="$1"; shift
  echo "==> [$name] $*" >&2
  if "$@"; then results+=("PASS  $name"); else results+=("FAIL  $name"); return 1; fi
}

deps_gate() {
  local touched
  touched="$(grep -E '(^|/)(package\.json|requirements[^/]*\.txt|constraints\.txt|pyproject\.toml)$' <<<"$changed" || true)"
  if [ -n "$touched" ] && [ "${ALLOW_DEPS:-0}" != 1 ]; then
    echo "dependency manifests changed vs $BASE (only W0-TH may add deps; ALLOW_DEPS=1 to acknowledge):" >&2
    echo "$touched" >&2
    return 1
  fi
}

mcp_suite() {  # mcp_suite <dir>
  local dir="$1" name="sheetstorm-verify-${RUN_ID}-$1"
  containers+=("$name")
  COPYFILE_DISABLE=1 tar -C "$ROOT/$dir" --exclude='__pycache__' --exclude='.pytest_cache' \
      --exclude='.venv' --exclude='._*' -cf - . | \
    docker run -i --rm --name "$name" -e PIP_DISABLE_PIP_VERSION_CHECK=1 --entrypoint sh "$PY_IMAGE" -c \
      'mkdir -p /src && tar -xf - -C /src && cd /src &&
       pip install -q --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r requirements-dev.lock &&
       PYTHONPATH=/src exec python -m pytest -q -p no:cacheprovider tests' &
  wait $!
}

frontend_gates() {
  (cd frontend && npm ci --ignore-scripts --legacy-peer-deps --no-fund --no-audit) &&
  (cd frontend && npx tsc --noEmit) &&
  (cd frontend && npm run lint) &&
  (cd frontend && TZ=UTC npm test -- --ci) &&
  (cd frontend && npm run build)
}

echo "verify-wp: WP_ID=$WP_ID BASE=$BASE backend=$run_backend mcp=$run_mcp frontend=$run_frontend e2e=$run_e2e" >&2
failed=0
gate deps deps_gate || failed=1
if [ "$run_backend" = 1 ]; then
  gate backend env IMAGE="sheetstorm-backend-test-${WP_ID}" TEST_RUN_ID="verify-${RUN_ID}" \
    bash backend/tests/run_in_docker.sh -q || failed=1
fi
if [ "$run_mcp" = 1 ]; then
  gate mcp-server mcp_suite mcp-server || failed=1
  gate mcp-bridge mcp_suite mcp-bridge || failed=1
fi
if [ "$run_frontend" = 1 ]; then
  gate frontend frontend_gates || failed=1
fi
if [ "$run_e2e" = 1 ]; then
  gate e2e-smoke bash -c 'cd frontend && npx playwright test --grep @smoke' || failed=1
fi

echo >&2
printf '%s\n' "${results[@]}" >&2
exit "$failed"
