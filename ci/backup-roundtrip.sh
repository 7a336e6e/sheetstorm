#!/usr/bin/env bash
# Backup -> destroy -> restore round trip against a THROWAWAY compose stack,
# proving scripts/backup.sh and scripts/restore.sh bring back the same data.
#
#   COMPOSE_PROJECT_NAME=sheetstorm-ci ci/backup-roundtrip.sh
#
# It runs `docker compose down -v`, so it refuses any project whose name does
# not start with sheetstorm-ci or sheetstorm-test.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
case "${COMPOSE_PROJECT_NAME:-}" in
  sheetstorm-ci*|sheetstorm-test*) ;;
  *) echo "roundtrip: set COMPOSE_PROJECT_NAME=sheetstorm-ci... (this deletes the stack's volumes)" >&2; exit 2 ;;
esac
dc() { docker compose "$@"; }

# Row count of every domain table, plus a digest of every evidence file.
# Tables that background jobs or sign-ins touch on their own are left out.
fingerprint() {
  dc exec -T database sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -F" " -c "
    SELECT table_name,
           (xpath(\$\$/row/c/text()\$\$, query_to_xml(format(\$\$SELECT count(*) AS c FROM public.%I\$\$, table_name), false, true, \$\$\$\$)))[1]::text
      FROM information_schema.tables
     WHERE table_schema = \$\$public\$\$ AND table_type = \$\$BASE TABLE\$\$
       AND table_name NOT IN (\$\$sessions\$\$, \$\$audit_logs\$\$, \$\$ledger_heads\$\$, \$\$reminder_log\$\$, \$\$notifications\$\$)
     ORDER BY 1"'
  dc exec -T backend sh -c \
    'cd "${LOCAL_ARTIFACT_DIR:-/app/artifacts}" && find . -type f -exec sha256sum {} + | sort | sha256sum | sed "s/^/artifacts /"'
}

before="$(fingerprint)"
echo "roundtrip: fingerprint before backup:" >&2
echo "$before" | grep -vE ' 0$' >&2

out="$(scripts/backup.sh "$(mktemp -d)" | tail -n 1)"

echo "roundtrip: destroying the stack and its volumes..." >&2
dc down -v --remove-orphans
dc up -d --wait

scripts/restore.sh "$out" --yes

after="$(fingerprint)"
if [ "$before" != "$after" ]; then
  echo "roundtrip: FAILED - restored data differs:" >&2
  diff <(echo "$before") <(echo "$after") >&2 || true
  exit 1
fi
rows="$(echo "$after" | awk '$1 != "artifacts" {s += $2} END {print s}')"
echo "roundtrip: OK - ${rows} rows across $(echo "$after" | grep -vc '^artifacts') tables and the evidence volume restored identically" >&2
rm -rf "$out"
