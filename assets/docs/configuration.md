# Configuration

## Environment Variables

Copy `.env.example` to `.env` and configure (`start.sh` does this and auto-generates `SECRET_KEY`, `JWT_SECRET_KEY` and `FERNET_KEY` on first run). `.env` is git-ignored; never commit it. `docker-compose.yml` passes the variables below through to the containers.

### Core

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_ENV` | No | `production` | `production` or `development`. Production refuses to start with default signing secrets and enables Secure cookies. `development` enables the Werkzeug debugger - never use it on a shared host. |
| `SECRET_KEY` | Yes | - | Flask secret key |
| `JWT_SECRET_KEY` | Yes | - | JWT signing key |
| `FERNET_KEY` | Yes | - | Fernet key encrypting integration credentials at rest |
| `CUSTODY_SIGNING_KEY` | Recommended | falls back to `SECRET_KEY` (startup warning) | HMAC key for chain-of-custody signatures. See [Custody signing key](#custody-signing-key-and-rotation) |
| `DATABASE_URL` | Yes | built by compose | PostgreSQL connection (compose builds it from `POSTGRES_*`) |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection (rate limiting, MCP OAuth state) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | No | `sheetstorm` / `changeme` / `sheetstorm` | PostgreSQL credentials - change the password for any shared deployment |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | No | `admin@sheetstorm.local` / `changeme` | Seeded admin account. Change the password after first login |

### Network, cookies and CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `FRONTEND_URL` | empty | Public base URL of the UI (OAuth redirects, links), e.g. `https://sheetstorm.example.com` |
| `CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the API with credentials (also used for Socket.IO). Empty means localhost-only defaults plus `FRONTEND_URL`. **Required when users reach SheetStorm via any non-localhost host.** |
| `JWT_COOKIE_SECURE` | `true` in production | Marks auth cookies `Secure` (HTTPS only). See [HTTPS and cookies](#https-and-cookies) |
| `JWT_REFRESH_GRACE_SECONDS` | `30` | How long a just-rotated refresh token is still accepted once (multi-tab refresh races) |
| `TRUSTED_PROXY_CIDRS` / `REAL_IP_HEADER` | empty / `X-Forwarded-For` | Upstream proxies trusted for the client IP; see [Running behind a reverse proxy / CDN](#running-behind-a-reverse-proxy--cdn) |
| `RATE_LIMIT_DEFAULT` | `600 per minute` | Default Flask-Limiter limit for API routes |
| `NEXT_PUBLIC_API_URL` | `/api/v1` | Backend API URL for the frontend (build-time). Relative paths work through the proxy on any host |
| `NEXT_PUBLIC_WS_URL` | empty | WebSocket URL for the frontend (build-time); empty means same origin |

### Outbound requests and enrichment

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTBOUND_URL_ALLOWLIST` | empty | Comma-separated hosts/CIDRs that admin-configured self-hosted integrations (MISP, Velociraptor, TheHive, Ollama, MinIO, ...) may target even though they resolve to private addresses, e.g. `ollama,misp.internal,10.0.0.0/8`. Private, loopback and metadata addresses are blocked otherwise (SSRF protection); link-local/cloud-metadata addresses are always blocked. |
| `PLATFORM_ORG_SLUG` | `default` | Slug of the platform organization. Only holders of `system:manage` in this organization are platform administrators (instance-wide settings). Self-registration is closed by default; an organization manager of the `default` organization enables it in Settings → General (installs upgraded from before `admin_guardrails_rbac` keep it open). |
| `IOC_AUTO_ENRICH` | `false` | Automatically send newly added IOCs to configured threat-intel integrations. Off by default because it discloses indicators to third parties. An organization-level setting overrides this default. |

### AI providers

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | empty | OpenAI API key for AI reports |
| `GOOGLE_AI_API_KEY` | empty | Google Gemini API key |
| `OPENAI_COMPATIBLE_API_KEY` | empty | Key for a generic OpenAI-compatible server (vLLM, LM Studio, llama.cpp). Never mixed with `OPENAI_API_KEY` |
| `OPENAI_BASE_URL` | empty | Base URL for the OpenAI-compatible provider |
| `OLLAMA_BASE_URL` | empty | Ollama base URL, e.g. `http://ollama:11434` (add `ollama` to `OUTBOUND_URL_ALLOWLIST`) |
| `LOCAL_LLM_MODEL` | empty | Default model name for local providers |
| `LOCAL_LLM_TIMEOUT` | `120` | Seconds before local LLM requests time out |

An optional local LLM container is available: `docker compose --profile local-llm up -d`. Its port is not published to the host; the backend reaches it at `http://ollama:11434` over the compose network.

### Storage, integrations and SSO (all optional; most are also configurable in the UI)

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | empty | S3-compatible storage credentials |
| `S3_BUCKET` / `S3_REGION` | `sheetstorm-artifacts` / `us-east-1` | Bucket and region |
| `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_REDIRECT_URI`, `GOOGLE_DRIVE_FOLDER_ID` | empty | Google Drive evidence storage |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_OAUTH_REDIRECT_URI` | empty | GitHub SSO |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | empty | Supabase SSO (backend) |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | empty | Supabase SSO (frontend, build-time) |
| `SLACK_WEBHOOK_URL` | empty | Slack webhook for notifications |

Without S3 or Google Drive, evidence is stored on the local `artifacts_data` Docker volume (mounted at `/app/artifacts`). Back this volume up like the database.

### MCP server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ISSUER_URL` | `http://localhost:8811` | Public URL clients reach the MCP server at; must match the host/proxy exactly |
| `MCP_ALLOWED_REDIRECT_HOSTS` | empty | Extra hostnames MCP OAuth clients may redirect to after login (comma-separated). Loopback redirects are always allowed. |
| `MCP_LOG_LEVEL` | `INFO` | MCP server log level |

MCP authentication is OAuth 2.1 (users sign in with their SheetStorm account); there is no static transport token. See `mcp-server/.env.example` for stdio-bridge settings.

## HTTPS and cookies

Browser sessions use httpOnly auth cookies. In production they are marked `Secure`, so browsers only store them over HTTPS. Choose one:

- **Recommended:** terminate TLS in front of the bundled proxy (Cloudflare Tunnel, a load balancer, Caddy/Traefik, ...) and forward `X-Forwarded-Proto: https`. Set `FRONTEND_URL` and `CORS_ORIGINS` to the public `https://` origin.
- **Local use:** `http://localhost:8080` / `http://127.0.0.1:8080` work in Chrome and Firefox (they accept `Secure` cookies on loopback). Safari does not - use `JWT_COOKIE_SECURE=false` or HTTPS.
- **Plain HTTP on any other host or IP** (e.g. `http://192.168.1.10:8080`): login appears to succeed but the browser drops the cookies. Either use HTTPS or set `JWT_COOKIE_SECURE=false` on a trusted network only.

If you serve the UI from a hostname other than localhost, also set `CORS_ORIGINS` (and `FRONTEND_URL`) to that exact origin, e.g. `CORS_ORIGINS=https://sheetstorm.example.com`; otherwise API and Socket.IO requests are rejected by CORS.

## Running behind a reverse proxy / CDN

The bundled nginx proxy (`proxy/`) decides the client IP that the backend uses for rate limiting, audit logs and chain-of-custody records.

**Default (secure):** no upstream proxy is trusted. nginx uses the TCP peer address and ignores client-supplied `X-Forwarded-For`, `X-Real-IP`, `CF-Connecting-IP`, `X-Forwarded-Proto` and `X-Forwarded-Host`. This is correct when SheetStorm is exposed directly. The backend then sees exactly one `X-Forwarded-For` hop (nginx's view), which it trusts.

**Opt in** when another proxy sits in front of the bundled one:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUSTED_PROXY_CIDRS` | empty | Comma/space-separated IPs or CIDRs (IPv4 and IPv6) of the proxies nginx may trust. Validated at container start: an invalid entry (or `/0`) stops the container with an error. |
| `REAL_IP_HEADER` | `X-Forwarded-For` | Header carrying the client IP. One of `X-Forwarded-For`, `X-Real-IP`, `CF-Connecting-IP`, `True-Client-IP`. |

The nginx realip config is rendered from these at container start (`proxy/docker-entrypoint-realip.sh`) with `real_ip_recursive on`, so a chain such as `client, proxy1, proxy2` resolves to the first address that is not a trusted proxy. `X-Forwarded-Proto`, `X-Forwarded-Host`-derived scheme and CDN geo headers (`CF-IPCountry`, ...) are only believed when the connecting peer is trusted; HSTS is only sent when the effective scheme is HTTPS.

> **Security warning:** list only proxies you control. If you trust a range that untrusted parties can reach, any client can forge its IP in rate limits, audit logs and chain-of-custody records. After changing the variables, run `docker compose up -d proxy` (no rebuild needed).

Examples (put in `.env`):

```bash
# Cloudflare (proxied DNS) - preset list shipped in the repo
# 1) run: paste -sd, proxy/presets/cloudflare-ips.txt
# 2) set TRUSTED_PROXY_CIDRS to its output (a comma-separated list):
TRUSTED_PROXY_CIDRS=173.245.48.0/20,103.21.244.0/22,...,2c0f:f248::/32
REAL_IP_HEADER=CF-Connecting-IP
# refresh the list from https://www.cloudflare.com/ips-v4 and /ips-v6 occasionally

# cloudflared (Tunnel) on the Docker host: nginx sees the compose network gateway as the peer.
# Find it with: docker network inspect <project>_default --format '{{(index .IPAM.Config 0).Gateway}}'
TRUSTED_PROXY_CIDRS=172.18.0.1/32
REAL_IP_HEADER=CF-Connecting-IP

# Traefik / Caddy / HAProxy / nginx on the same Docker network or host
TRUSTED_PROXY_CIDRS=172.18.0.0/16        # the network that proxy connects from
REAL_IP_HEADER=X-Forwarded-For

# AWS ALB / GCP / Azure load balancer: the VPC or subnet range of the load balancer
TRUSTED_PROXY_CIDRS=10.0.0.0/16
REAL_IP_HEADER=X-Forwarded-For
```

Note that `.env` does not run shell substitutions: generate the value first (`paste -sd, proxy/presets/cloudflare-ips.txt`) and paste the result.

The proxy publishes port `8080` on all interfaces by default. Bind it to a specific address in `docker-compose.yml` (e.g. `"127.0.0.1:8080:80"`) if it should not be reachable from the network.

## Database migrations

The backend entrypoint runs `flask db upgrade` on every container start, so a fresh `docker compose up` creates the full schema. If the database is not reachable yet it retries up to 5 times with exponential backoff (`MIGRATION_MAX_ATTEMPTS` overrides) and then **exits with an error** - the container will restart and `docker compose logs backend` shows the failure. The API never starts against a half-migrated schema. The admin user is seeded by `start.sh` (or manually: `docker compose exec backend python -c "from app.seed import seed_all; seed_all()"`).

## Custody signing key and rotation

Chain-of-custody entries are signed with an HMAC keyed by `CUSTODY_SIGNING_KEY`. Generate it once, keep it in your secret store, and back it up with the database:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

- Set it **before** recording evidence. If it is unset the backend falls back to `SECRET_KEY`, which means rotating `SECRET_KEY` would invalidate every custody signature. When migrating an existing install off the fallback, set `CUSTODY_SIGNING_KEY` to the current `SECRET_KEY` value so existing signatures keep verifying, then rotate `SECRET_KEY` freely.
- Rotating `CUSTODY_SIGNING_KEY` itself makes signatures created with the old key fail verification. Avoid rotating during active cases. If you must rotate (suspected key exposure), first verify and export the custody records of open cases, archive the old key securely together with that export, then record the rotation date in the affected cases.
- Never reuse the custody key for anything else and never commit it.

## Database Schema

23 tables with UUID primary keys, automatic `updated_at` triggers, and auto-incrementing incident numbers per organization.

**Key Tables**: `users`, `roles`, `user_roles`, `organizations`, `incidents`, `incident_assignments`, `timeline_events`, `compromised_hosts`, `compromised_accounts`, `network_indicators`, `host_based_indicators`, `malware_tools`, `attack_graph_nodes`, `attack_graph_edges`, `artifacts`, `chain_of_custody`, `tasks`, `task_comments`, `reports`, `notifications`, `audit_logs`, `integrations`, `teams`, `team_members`.

**Extensions**: `uuid-ossp` (UUID generation), `pgcrypto` (cryptographic functions).
