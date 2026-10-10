#!/usr/bin/env bash
# Back up a running SheetStorm docker compose deployment: the PostgreSQL
# database and the local evidence volume, with a checksummed manifest.
#
#   scripts/backup.sh                  # writes ./backups/sheetstorm-backup-<UTC>/
#   scripts/backup.sh /srv/backups     # another parent directory
#
# Output (directory mode 0700, files 0600 - the dump holds case data):
#   database.dump   pg_dump custom format, taken inside the database container
#                   (its pg_dump always matches the server version)
#   artifacts.tar   the evidence volume (LOCAL_ARTIFACT_DIR in the backend)
#   manifest.json   time, Alembic revision, app version, sha256 of each file
#
# The backup is online: the database dump is one consistent snapshot, and the
# evidence files are copied after it, so every file the dump references is in
# the archive. Not included: the .env file (keep FERNET_KEY, CUSTODY_SIGNING_KEY,
# AUDIT_CHAIN_KEY, SECRET_KEY and JWT_SECRET_KEY safe separately - see
# assets/docs/operations.md), Redis (sessions and rate-limit counters only), and
# evidence stored in S3 or Google Drive (back those up at the provider).
#
# docker compose settings come from the usual variables, e.g.
# COMPOSE_PROJECT_NAME, COMPOSE_FILE. Restore with scripts/restore.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PARENT="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${PARENT%/}/sheetstorm-backup-${STAMP}"
dc() { docker compose "$@"; }

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

running="$(dc ps --status running --services)"
for svc in database backend; do
  grep -qx "$svc" <<<"$running" || { echo "backup: service '$svc' is not running" >&2; exit 1; }
done

umask 077
mkdir -p "$OUT"
# A failed backup must not leave a directory that looks complete.
trap 'status=$?; [ "$status" -eq 0 ] || { rm -rf "$OUT"; echo "backup: failed, removed $OUT" >&2; }' EXIT

echo "backup: dumping the database..." >&2
dc exec -T database sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/database.dump"

echo "backup: archiving the evidence volume..." >&2
dc exec -T backend sh -c 'tar -C "${LOCAL_ARTIFACT_DIR:-/app/artifacts}" -cf - .' > "$OUT/artifacts.tar"

revision="$(dc exec -T database sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
server="$(dc exec -T database sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SHOW server_version"' | tr -d '[:space:]')"
app_version="$(dc exec -T backend sh -c 'printf %s "${APP_VERSION:-}"')"
commit="$(git rev-parse HEAD 2>/dev/null || true)"

cat > "$OUT/manifest.json" <<EOF
{
  "format": 1,
  "created_at": "$(date -u +%FT%TZ)",
  "alembic_revision": "${revision}",
  "postgres_version": "${server}",
  "app_version": "${app_version}",
  "git_commit": "${commit}",
  "files": {
    "database.dump": {"sha256": "$(sha256 "$OUT/database.dump")", "bytes": $(wc -c < "$OUT/database.dump" | tr -d ' ')},
    "artifacts.tar": {"sha256": "$(sha256 "$OUT/artifacts.tar")", "bytes": $(wc -c < "$OUT/artifacts.tar" | tr -d ' ')}
  }
}
EOF

echo "backup: done -> $OUT" >&2
echo "backup: the .env file is NOT in the backup. Without the same FERNET_KEY," >&2
echo "        CUSTODY_SIGNING_KEY and AUDIT_CHAIN_KEY a restore cannot decrypt" >&2
echo "        integration credentials or verify custody and audit signatures." >&2
echo "$OUT"
