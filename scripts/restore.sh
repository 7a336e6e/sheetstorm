#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into this docker compose
# deployment. DESTRUCTIVE: the current database and evidence volume are
# replaced, so it refuses to run without --yes.
#
#   scripts/restore.sh backups/sheetstorm-backup-20261010T120000Z --yes
#
# Steps: verify the manifest checksums; check the backup's schema revision is
# known to this SheetStorm version; stop the application services; recreate
# the database and pg_restore into it; replace the evidence volume; start the
# stack (the backend applies any newer migrations); verify the audit chain.
#
# Restore with the SAME secrets the backup was taken with (.env: FERNET_KEY,
# CUSTODY_SIGNING_KEY, AUDIT_CHAIN_KEY, ...). Sessions are not restored: users
# sign in again. docker compose settings come from the usual variables
# (COMPOSE_PROJECT_NAME, COMPOSE_FILE).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKUP="" YES=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    -*) echo "restore: unknown option $arg" >&2; exit 2 ;;
    *) BACKUP="$arg" ;;
  esac
done
[ -n "$BACKUP" ] || { echo "usage: scripts/restore.sh <backup-dir> --yes" >&2; exit 2; }
BACKUP="$(cd "$BACKUP" && pwd)"
cd "$ROOT"
dc() { docker compose "$@"; }

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}
manifest_value() {  # manifest_value <key> : first "key": "value" in the manifest
  sed -n "s/.*\"$1\": *\"\\([^\"]*\\)\".*/\\1/p" "$BACKUP/manifest.json" | head -n 1
}

for f in manifest.json database.dump artifacts.tar; do
  [ -f "$BACKUP/$f" ] || { echo "restore: $BACKUP/$f is missing" >&2; exit 1; }
done
for f in database.dump artifacts.tar; do
  want="$(grep "\"$f\"" "$BACKUP/manifest.json" | sed -n 's/.*"sha256": *"\([0-9a-f]*\)".*/\1/p')"
  have="$(sha256 "$BACKUP/$f")"
  [ -n "$want" ] && [ "$want" = "$have" ] || { echo "restore: checksum mismatch for $f" >&2; exit 1; }
done
revision="$(manifest_value alembic_revision)"
echo "restore: backup $(basename "$BACKUP") (created $(manifest_value created_at), schema ${revision:-unknown}); checksums OK" >&2

if [ "$YES" != 1 ]; then
  echo "restore: this REPLACES the current database and evidence files. Re-run with --yes." >&2
  exit 2
fi

echo "restore: starting database and redis..." >&2
dc up -d --wait database redis

# A backup from a newer SheetStorm has a schema revision this image does not
# know; migrations would fail after the data is already replaced. Check first.
if [ -n "$revision" ]; then
  dc run --rm --no-deps -T --entrypoint sh backend -c \
    "grep -rqE \"^revision *= *['\\\"]${revision}['\\\"]\" migrations/versions" || {
    echo "restore: schema revision ${revision} is unknown to this SheetStorm version." >&2
    echo "         Upgrade SheetStorm to the version the backup was taken with (or newer) first." >&2
    exit 1
  }
fi

app_services=()
for svc in proxy frontend mcp-server jobs backend; do
  dc config --services | grep -qx "$svc" && app_services+=("$svc")
done
echo "restore: stopping ${app_services[*]}..." >&2
dc stop "${app_services[@]}" >/dev/null

echo "restore: recreating the database..." >&2
dc exec -T database sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
dc exec -T database sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error --single-transaction' \
  < "$BACKUP/database.dump"

echo "restore: replacing the evidence volume..." >&2
dc run --rm --no-deps -T --entrypoint sh backend -c \
  'dir="${LOCAL_ARTIFACT_DIR:-/app/artifacts}"; find "$dir" -mindepth 1 -delete && tar -C "$dir" -xf -' \
  < "$BACKUP/artifacts.tar"

echo "restore: starting the stack (pending migrations run on backend start)..." >&2
dc up -d --wait

echo "restore: verifying the audit chain..." >&2
if dc exec -T -e FLASK_APP=app:create_app backend flask sheetstorm verify-audit-chain; then
  echo "restore: done" >&2
else
  echo "restore: data restored, but the audit chain did not verify. Check that AUDIT_CHAIN_KEY" >&2
  echo "         (and AUDIT_CHAIN_PREVIOUS_KEYS) match the deployment the backup came from." >&2
  exit 3
fi
