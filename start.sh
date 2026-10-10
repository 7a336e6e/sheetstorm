#!/bin/bash
set -e

# ─── Parse arguments ─────────────────────────────────────────────────────────

MODE="prod"  # default to production

RELEASE=""  # empty: build from source; X.Y.Z: run the published images

usage() {
    echo "Usage: $0 [--dev | --prod] [--version X.Y.Z]"
    echo ""
    echo "  --dev   Development mode  — skips cronjob setup, builds with no cache"
    echo "  --prod  Production mode   — installs daily MITRE data update cronjob (default)"
    echo "  --version X.Y.Z  Pull and run the published release images instead of"
    echo "                   building from source (writes SHEETSTORM_VERSION and"
    echo "                   COMPOSE_FILE to .env; see assets/docs/operations.md)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)  MODE="dev";  shift ;;
        --prod) MODE="prod"; shift ;;
        --version)
            [[ "${2:-}" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo "--version needs X.Y.Z"; usage; }
            RELEASE="${2#v}"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

MODE_UPPER=$(echo "$MODE" | tr '[:lower:]' '[:upper:]')
echo "==================================="
echo "SheetStorm - Incident Response Platform"
echo "Mode: ${MODE_UPPER}"
echo "==================================="

# ─── Ensure persistent data directories exist ────────────────────────────────

mkdir -p data/postgres data/redis

# ─── Check for .env file ─────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "WARNING: Please update .env with secure values before production use!"
fi

# ─── Generate keys if not set ─────────────────────────────────────────────────
# Only empty / "changeme*" placeholder values are replaced. An existing real value
# is NEVER overwritten: rotating SECRET_KEY / JWT_SECRET_KEY invalidates sessions,
# CUSTODY_SIGNING_KEY breaks chain-of-custody verification and FERNET_KEY makes
# stored integration credentials undecryptable.

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

# Set KEY=VALUE in .env (portable across BSD/GNU: awk + temp file, no `sed -i`).
# Only the line that starts exactly with "KEY=" is replaced; appended if missing.
# The value is passed via the environment so no character needs escaping.
set_env() {
    local tmp
    tmp=$(mktemp "${TMPDIR:-/tmp}/sheetstorm-env.XXXXXX")
    ENV_K="$1" ENV_V="$2" awk '
        BEGIN { k = ENVIRON["ENV_K"]; v = ENVIRON["ENV_V"]; done = 0 }
        index($0, k "=") == 1 { if (!done) { print k "=" v; done = 1 } ; next }
        { print }
        END { if (!done) print k "=" v }
    ' .env > "$tmp"
    cat "$tmp" > .env   # keep the original file's mode/ownership
    rm -f "$tmp"
}

gen_hex() {
    python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32
}

gen_fernet() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null \
        || openssl rand -base64 32 | tr '+/' '-_'
}

# ensure_key NAME GENERATOR — generate NAME only when empty or a placeholder.
ensure_key() {
    local name="$1" generator="$2" current
    current=$(get_env "$name")
    if [ -z "$current" ] || [[ "$current" == changeme* ]]; then
        echo "Generating $name..."
        set_env "$name" "$($generator)"
    fi
}

ensure_key SECRET_KEY gen_hex
ensure_key JWT_SECRET_KEY gen_hex
ensure_key FERNET_KEY gen_fernet
ensure_key CUSTODY_SIGNING_KEY gen_hex

# ─── Build (or pull) & start containers ──────────────────────────────────────

echo ""
if [ -n "$RELEASE" ]; then
    set_env SHEETSTORM_VERSION "$RELEASE"
    set_env COMPOSE_FILE "docker-compose.yml:docker-compose.images.yml"
    echo "Pulling release images ${RELEASE}..."
    docker compose pull
else
    echo "Building containers..."
    docker compose build
fi

echo ""
echo "Starting services..."
docker compose up -d

echo ""
echo "Waiting for backend to become healthy (entrypoint runs migrations and fails fast)..."
BACKEND_ID=$(docker compose ps -q backend)
WAIT_TIMEOUT=300
WAITED=0
while true; do
    STATE=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$BACKEND_ID" 2>/dev/null || echo "missing")
    case "$STATE" in
        healthy|running) break ;;
        exited|dead|missing)
            echo "ERROR: backend container is $STATE (migrations or startup checks failed). Last logs:"
            docker compose logs --tail 50 backend || true
            exit 1 ;;
    esac
    if [ "$WAITED" -ge "$WAIT_TIMEOUT" ]; then
        echo "ERROR: backend not healthy after ${WAIT_TIMEOUT}s (state: $STATE). Last logs:"
        docker compose logs --tail 50 backend || true
        exit 1
    fi
    sleep 3
    WAITED=$((WAITED + 3))
done
echo "Backend is $STATE."

echo ""
echo "Seeding initial data..."
docker compose exec -T backend python -c "from app.seed import seed_all; seed_all()" || echo "Seeding may have already run"

# ─── Cronjob setup (prod only) ───────────────────────────────────────────────

if [ "$MODE" = "prod" ]; then
    echo ""
    echo "Setting up daily MITRE data update cronjob..."
    CRON_CMD="0 3 * * * cd $(pwd) && ./update_mitre_data.sh"
    # Remove any existing SheetStorm MITRE cron entries, then add the new one
    ( crontab -l 2>/dev/null | grep -v 'update_mitre_data.sh' ; echo "$CRON_CMD" ) | crontab -
    echo "Cronjob installed: daily at 03:00 — updates ATT&CK and D3FEND data"
else
    echo ""
    echo "Dev mode — skipping cronjob setup"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "==================================="
echo "SheetStorm is running! (${MODE_UPPER})"
echo "==================================="
echo ""
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || true)
fi
echo "App (via proxy): http://127.0.0.1:8080"
if [ -n "$LAN_IP" ]; then
    echo "App (LAN):       http://${LAN_IP}:8080"
    echo ""
    echo "NOTE: production auth cookies are Secure, so logging in over plain HTTP from any"
    echo "      host other than localhost/127.0.0.1 (e.g. http://${LAN_IP}:8080) will fail unless you"
    echo "      either serve SheetStorm over HTTPS, or set JWT_COOKIE_SECURE=false in .env"
    echo "      (trusted networks only). In both cases add that origin to CORS_ORIGINS and set"
    echo "      FRONTEND_URL in .env, otherwise real-time (WebSocket) updates are rejected."
    echo "      Then run: docker compose up -d"
fi
echo "Frontend (direct): http://127.0.0.1:3000"
echo "Backend API (direct): http://127.0.0.1:5000/api/v1"
echo ""
echo "Default admin credentials:"
echo "  Email: admin@sheetstorm.local"
echo "  Password: ADMIN_PASSWORD from .env, or the generated one printed by the seed step above"
echo "            (first run only; you must change it at first sign-in)"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop: docker compose down"
echo ""
