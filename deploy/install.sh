#!/usr/bin/env bash
# SheetStorm installer for the release bundle
# (https://github.com/7a336e6e/sheetstorm/releases): runs the published,
# signed container images with Docker Compose. No source checkout needed.
#
#   ./install.sh              first install, or an upgrade after unpacking a newer bundle here
#   ./install.sh --env-only   only create .env / fill in missing secrets (start.sh uses this)
#
# Works in the current directory (the one holding docker-compose.yml):
#   1. .env is created from .env.example on the first run, with fresh random
#      secrets (database password, SECRET_KEY, JWT_SECRET_KEY, FERNET_KEY,
#      CUSTODY_SIGNING_KEY, AUDIT_CHAIN_KEY, API_KEY_PEPPER) and mode 0600.
#      An existing .env is kept: only empty / "changeme" values of the four
#      core keys are filled in (an existing install without
#      CUSTODY_SIGNING_KEY gets its current SECRET_KEY, which signed its
#      custody entries so far). Never regenerate keys of a running install:
#      FERNET_KEY decrypts stored credentials, CUSTODY_SIGNING_KEY and
#      AUDIT_CHAIN_KEY verify signatures made earlier.
#   2. docker compose pull + up --wait (the backend applies migrations).
#   3. The first administrator is created on a fresh database; with
#      ADMIN_PASSWORD empty its one-time password is printed once.
set -euo pipefail

ENV_ONLY=0
case "${1:-}" in
  --env-only) ENV_ONLY=1 ;;
  -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
  "") ;;
  *) echo "install: unknown option $1 (see --help)" >&2; exit 2 ;;
esac

# ─── .env helpers ───────────────────────────────────────────────────────────

# Print the value of KEY from .env (last occurrence, surrounding quotes stripped).
get_env() {
  local line
  line=$(grep -E "^$1=" .env | tail -n 1) || true
  line=${line#*=}
  line=${line%$'\r'}
  case "$line" in
    \"*\") line=${line#\"}; line=${line%\"} ;;
    \'*\') line=${line#\'}; line=${line%\'} ;;
  esac
  printf '%s' "$line"
}

# Set KEY=VALUE in .env (portable: awk + temp file, no `sed -i`). Only the line
# starting exactly with "KEY=" is replaced; appended when missing. The value is
# passed through the environment so no character needs escaping.
set_env() {
  local tmp
  tmp=$(mktemp "${TMPDIR:-/tmp}/sheetstorm-env.XXXXXX")
  ENV_K="$1" ENV_V="$2" awk '
    BEGIN { k = ENVIRON["ENV_K"]; v = ENVIRON["ENV_V"]; done = 0 }
    index($0, k "=") == 1 { if (!done) { print k "=" v; done = 1 } ; next }
    { print }
    END { if (!done) print k "=" v }
  ' .env > "$tmp"
  cat "$tmp" > .env   # keep the file's mode and ownership
  rm -f "$tmp"
}

gen_hex() {  # gen_hex [bytes]
  openssl rand -hex "${1:-32}" 2>/dev/null || python3 -c "import secrets, sys; print(secrets.token_hex(int(sys.argv[1])))" "${1:-32}"
}

gen_fernet() {  # urlsafe base64 of 32 random bytes
  python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" 2>/dev/null \
    || openssl rand -base64 32 | tr '+/' '-_'
}

# Generate NAME only when it is empty or a "changeme" placeholder.
ensure_key() {
  local name="$1" generator="$2" current
  current=$(get_env "$name")
  if [ -z "$current" ] || [[ "$current" == changeme* ]]; then
    echo "install: generating $name"
    set_env "$name" "$($generator)"
  fi
}

# Whether this compose project already has a database volume (a .env deleted
# from an existing install must not get a new database password or audit key).
# The resolved volume name comes from compose itself (project-scoped).
database_volume_exists() {
  local volume
  volume=$(docker compose config --format json 2>/dev/null | tr -d ' \n' \
    | sed -n 's/.*"postgres_data":{"name":"\([^"]*\)".*/\1/p')
  [ -n "$volume" ] && docker volume inspect "$volume" >/dev/null 2>&1
}

setup_env() {
  local existing_install=0
  if [ ! -f .env ]; then
    local template=""
    for t in .env.example env.example; do [ -f "$t" ] && template=$t && break; done
    [ -n "$template" ] || { echo "install: no .env and no .env.example here" >&2; exit 1; }
    ( umask 077; cp "$template" .env )
    chmod 600 .env
    echo "install: created .env from $template"
    if database_volume_exists; then
      existing_install=1
      echo "install: WARNING: a database volume already exists but .env was missing." >&2
      echo "         Restore the original .env (database password, FERNET_KEY, signing keys)." >&2
    else
      local pg
      pg=$(gen_hex 16)
      set_env POSTGRES_PASSWORD "$pg"
      set_env DATABASE_URL "postgresql://$(get_env POSTGRES_USER):${pg}@database:5432/$(get_env POSTGRES_DB)"
      set_env AUDIT_CHAIN_KEY "$(gen_hex 32)"
      set_env API_KEY_PEPPER "$(gen_hex 32)"
    fi
  elif database_volume_exists; then
    existing_install=1
  fi
  # Without CUSTODY_SIGNING_KEY the backend signs custody entries with
  # SECRET_KEY. On an existing install keep exactly that key (the documented
  # migration), so signatures made so far keep verifying; a new random key
  # would break them. Done before SECRET_KEY is touched.
  local custody
  custody=$(get_env CUSTODY_SIGNING_KEY)
  if [ "$existing_install" = 1 ] && { [ -z "$custody" ] || [[ "$custody" == changeme* ]]; } \
      && [ -n "$(get_env SECRET_KEY)" ]; then
    echo "install: setting CUSTODY_SIGNING_KEY to the current SECRET_KEY (existing custody signatures keep verifying)"
    set_env CUSTODY_SIGNING_KEY "$(get_env SECRET_KEY)"
  fi
  ensure_key SECRET_KEY gen_hex
  ensure_key JWT_SECRET_KEY gen_hex
  ensure_key FERNET_KEY gen_fernet
  ensure_key CUSTODY_SIGNING_KEY gen_hex
}

setup_env
[ "$ENV_ONLY" = 1 ] && exit 0

# ─── Pull, start, first admin ───────────────────────────────────────────────

docker compose version >/dev/null 2>&1 || { echo "install: Docker Compose v2 is required" >&2; exit 1; }
[ -f docker-compose.yml ] || [ -f compose.yaml ] || { echo "install: run it next to docker-compose.yml" >&2; exit 1; }

echo "install: pulling images..."
docker compose pull
echo "install: starting SheetStorm (the backend applies database migrations)..."
docker compose up -d --wait --wait-timeout 600
echo "install: creating the first administrator (skipped when it exists)..."
docker compose exec -T backend python -c "from app.seed import seed_all; seed_all()"

cat <<EOF

SheetStorm is running: http://localhost:8080
  - Sign in as $(get_env ADMIN_EMAIL). Without ADMIN_PASSWORD in .env, the
    one-time password is printed above (first install only); you choose a new
    one at first sign-in.
  - Other host names need TLS in front of the proxy and FRONTEND_URL /
    CORS_ORIGINS in .env (see README.md).
  - Keep .env safe and back it up separately: scripts/backup.sh covers the
    database and evidence, not the keys.
  - Upgrade: unpack a newer bundle over this directory (.env is kept), back
    up, then run ./install.sh again.
EOF
