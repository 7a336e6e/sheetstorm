#!/usr/bin/env bash
# Regenerate the hash-locked Python lockfiles from the human-edited inputs.
# Policy and bump procedure: assets/docs/supply-chain.md ("Hash-locked Python").
#
#   scripts/lock-python.sh                                    # cutoff = exactly 7 days ago (UTC)
#   EXCLUDE_NEWER=2026-10-01T00:00:00Z scripts/lock-python.sh # explicit cutoff
#
#   input (edit this)                          -> lockfile (generated, commit it)
#   backend/requirements.txt                   -> backend/requirements.lock
#   backend/requirements-dev.txt               -> backend/requirements-dev.lock
#   mcp-server/constraints.txt                 -> mcp-server/requirements.lock
#   mcp-server/build-requirements.txt          -> mcp-server/build-requirements.lock
#   mcp-server/{constraints,requirements-dev,build-requirements}.txt
#                                              -> mcp-server/requirements-dev.lock
#   mcp-bridge/requirements.txt                -> mcp-bridge/requirements.lock
#   mcp-bridge/requirements{,-dev}.txt         -> mcp-bridge/requirements-dev.lock
#
# uv runs inside a throwaway, digest-pinned container: nothing is installed on
# the host and no host environment (tokens, cloud credentials) is passed in.
# --exclude-newer makes anything uploaded after the cutoff invisible, so a lock
# can never pick up a release younger than the cooldown. Locks are --universal:
# every wheel/sdist hash of each pinned version is recorded, so the same file
# installs on linux/amd64 + linux/arm64 (Docker) and on developer machines.
# Dev locks are constrained to the runtime lock, so shared packages never drift.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# A full RFC 3339 timestamp, not a date: uv treats a bare date as the end of
# that day, which let in files uploaded up to ~24 h after the intended cutoff.
EXCLUDE_NEWER="${EXCLUDE_NEWER:-$(date -u -v-7d +%FT%TZ 2>/dev/null || date -u -d '7 days ago' +%FT%TZ)}"
# uv 0.12.21 (released 2026-09-29) with CPython 3.12; bump the digest via
# `docker buildx imagetools inspect ghcr.io/astral-sh/uv:<ver>-python3.12-trixie-slim`.
UV_IMAGE="ghcr.io/astral-sh/uv:0.12.21-python3.12-trixie-slim@sha256:5ae92e4d35b8d586d50ddf4aba6ecdd9f744237284d31c86bf45077e4e17e4bd"

echo "Locking with --exclude-newer ${EXCLUDE_NEWER} (nothing uploaded after this moment resolves)"

docker run --rm --network bridge \
  -e EXCLUDE_NEWER="$EXCLUDE_NEWER" -e UV_NO_CONFIG=1 -e UV_CACHE_DIR=/tmp/uv-cache \
  -v "$ROOT:/src" -w /src --entrypoint /bin/sh "$UV_IMAGE" -euc '
compile() {  # compile <python-version> <output> <inputs/flags...>
  pyver="$1"; out="$2"; shift 2
  uv pip compile --quiet --generate-hashes --universal --python-version "$pyver" \
    --exclude-newer "$EXCLUDE_NEWER" --index-url https://pypi.org/simple \
    --custom-compile-command "scripts/lock-python.sh  (EXCLUDE_NEWER=$EXCLUDE_NEWER)" \
    --output-file "$out" "$@"
  echo "  $out: $(grep -c "^[A-Za-z0-9]" "$out") packages"
}
# Hash-free copy of a lock, usable as a constraints file for the dev lock.
pins() { grep -E "^[A-Za-z0-9]" "$1" | sed "s/ *\\\\$//" > "$2"; }

cd /src/backend
compile 3.12 requirements.lock requirements.txt
pins requirements.lock /tmp/backend-pins.txt
compile 3.12 requirements-dev.lock requirements-dev.txt -c /tmp/backend-pins.txt

cd /src/mcp-server
compile 3.12 requirements.lock constraints.txt
compile 3.12 build-requirements.lock build-requirements.txt
pins requirements.lock /tmp/mcp-pins.txt
compile 3.12 requirements-dev.lock constraints.txt requirements-dev.txt build-requirements.txt \
  -c /tmp/mcp-pins.txt

cd /src/mcp-bridge  # runs on user machines: resolve for every Python it supports
compile 3.11 requirements.lock requirements.txt
pins requirements.lock /tmp/bridge-pins.txt
compile 3.11 requirements-dev.lock requirements.txt requirements-dev.txt -c /tmp/bridge-pins.txt
'
echo "Done. Review the lockfile diff (git diff -- '*.lock'): only the packages you meant to change should move."
