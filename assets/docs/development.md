# Development Guide

## Docker Setup (Recommended)

```bash
git clone <repo-url> && cd SheetStorm
chmod +x start.sh && ./start.sh
```

This auto-generates secrets, builds all 6 containers, runs migrations (the backend entrypoint applies them on every start and fails loudly if they cannot be applied), and seeds the admin user.

See [Configuration](configuration.md) for environment variables, HTTPS/cookie requirements and `CORS_ORIGINS` when not using localhost.

## Manual Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install --require-hashes --no-deps -r requirements-dev.lock   # hash-locked runtime + test deps
flask db upgrade
python -c "from app.seed import seed_all; seed_all()"
flask run --debug

# Frontend (lockfile-only install; scripts are disabled by .npmrc)
cd frontend
npm ci --legacy-peer-deps
npm run dev
```

## Access Points

| Service  | URL                                |
|----------|------------------------------------|
| Frontend | http://127.0.0.1:3000              |
| Backend  | http://127.0.0.1:5000/api/v1       |
| Database | postgresql://localhost:5432        |
| Redis    | redis://localhost:6379             |

## Useful Commands

```bash
# View logs
docker compose logs -f backend

# Access database
docker compose exec database psql -U sheetstorm

# Flask shell
docker compose exec backend flask shell

# Rebuild single service
docker compose build backend && docker compose up -d backend
```

## Migrations

```bash
cd backend
flask db upgrade          # Apply all migrations
flask db migrate -m "..."  # Create new migration
flask db downgrade        # Rollback last migration
```

Search relies on the `pg_trgm` extension (enabled by `database/init/001_extensions.sql`
on fresh installs and by migration `add_search_trgm_indexes` on upgrades) and
one trigram GIN index per searchable table. The indexes are built with plain
(non-`CONCURRENTLY`) `CREATE INDEX`, which blocks writes to those tables while
it runs; on large existing databases run the upgrade in a maintenance window.
A new searchable entity adds a `SearchType` in
`backend/app/services/search_service.py` plus an index on
`index_expression_sql(...)` in a migration (`tests/test_search.py` checks parity).

## Production WSGI

```bash
gunicorn --worker-class eventlet -w 1 wsgi:app
```

## Testing

### Backend (pytest)

Backend tests live in `backend/tests/`. Test-only dependencies (pytest, pytest-cov) are in `requirements-dev.txt` / `requirements-dev.lock` and are installed only in the backend Dockerfile's `test` stage, not in the production image. Run the tests inside that image so the Python version and system libraries match production:

```bash
# Builds the `test` stage, starts throwaway Postgres + Redis, runs pytest
./backend/tests/run_in_docker.sh
./backend/tests/run_in_docker.sh -k custody -x   # extra args go to pytest
```

Runs are parallel-safe: every network/container is named `sheetstorm-test-<run-id>-*` (label `sheetstorm.test-run=<run-id>`) and removed on exit, including on Ctrl-C/TERM. `TEST_RUN_ID` sets the id (default: random). The default image tag is per run and untagged afterwards; set `IMAGE=sheetstorm-backend-test-<wp-id>` to keep a named tag. `KEEP=1` leaves everything in place for debugging (`docker rm -f $(docker ps -aq --filter label=sheetstorm.test-run=<id>)` to clean up).

Fixtures (`backend/tests/conftest.py`): `app`, `db`, `org_a`/`org_b`, `users` (one per system role in org A + `admin_b`), `auth(user, mode='bearer'|'cookie')`, `make_incident(...)`, `redis_client`, plus:

- `make_user(org, perms=None, roles=None, **kw)`: system roles and/or a fresh custom role holding exactly `perms`.
- `fresh_user(role='Analyst', org=None, **kw)`: a new user. Mutate this one, never the shared `users`.
- `platform_org` / `platform_admin`: the org with slug `PLATFORM_ORG_SLUG` (default `default`) and an Administrator in it.
- Feature fixtures go in `backend/tests/fixtures/<feature>.py`. Every module there is registered through `pytest_plugins` automatically; prefix fixture names with the feature.

Tests must not need real secrets: the testing config uses throwaway keys. Never point tests at a production database.

### MCP (pytest)

`scripts/verify-wp.sh --mcp` runs `mcp-server/tests` and `mcp-bridge/tests` in throwaway, digest-pinned `python:3.12-slim-bookworm` containers from each component's hash-locked `requirements-dev.lock`. Locally you can also follow each component's README (`pip install --require-hashes --no-deps -r requirements-dev.lock`, then `pytest`).

### Frontend unit and component tests (Jest)

Jest via `next/jest` (SWC transform, no Babel config) with `jest-environment-jsdom` and Testing Library (`@testing-library/react`, `@testing-library/jest-dom`). Not Vitest.

```bash
cd frontend
npm test                 # all of src/**/*.test.ts(x)
npm test -- store        # filter by path
npm run test:watch
npm run test:ci          # what the gates run
```

- Tests live next to the code as `src/**/*.test.ts` / `*.test.tsx`; `@/` imports work.
- The default environment is jsdom. Pure logic tests can opt into the faster node environment with `/** @jest-environment node */` as the first line.
- `frontend/jest.setup.ts` loads the jest-dom matchers and the shared jsdom shims (ResizeObserver, matchMedia, scrollIntoView, pointer capture). Add new browser shims there once, not per test.
- Mock at module boundaries: `jest.mock('./api')` for the API client (see `src/lib/store.test.ts`). Component tests render through real providers and query by role (see `src/components/ui/confirm-dialog.test.tsx`).
- `@testing-library/user-event` is not installed. Use `fireEvent` from `@testing-library/react`.

### E2E (Playwright)

Playwright (`@playwright/test`) runs against an **already-running** stack. The config never starts servers. Browsers are installed explicitly, never by an npm install script:

```bash
cd frontend
npx playwright install chromium              # once per machine / Playwright version
export E2E_BASE_URL=http://localhost:8080    # default: the compose proxy
export ADMIN_EMAIL=... ADMIN_PASSWORD=...    # bootstrap admin, from your .env (never committed)
npm run test:e2e:smoke                       # playwright test --grep @smoke
npm run test:e2e                             # everything
```

`e2e/global-setup.ts` seeds one user per system role through the API and saves each session to `frontend/e2e/.auth/<org>-<role>.json` (mode 0600, git- and docker-ignored). Without `ADMIN_EMAIL`/`ADMIN_PASSWORD` nothing is seeded and every logged-in spec skips. Specs call `useRole('viewer')` (from `e2e/fixtures.ts`) to run as a role. A second org for cross-org specs is bootstrapped with `frontend/e2e/seed-second-org.py`. See `frontend/e2e/README.md` for details.

E2E runs only on the integration branch, by the integrator, against a `docker compose up` stack. Work-package agents must not bring up the compose stack, because its container names and port 8080 are fixed.

### Merge gates (`scripts/verify-wp.sh`)

```bash
scripts/verify-wp.sh            # gates for what changed vs `integration` (or `main`)
scripts/verify-wp.sh --all      # backend + MCP + frontend
scripts/verify-wp.sh --e2e      # + Playwright @smoke against E2E_BASE_URL (integrator)
```

Gates: backend docker suite (includes the single-Alembic-head check in `test_migrations.py`), MCP suites, then for the frontend `npm ci --ignore-scripts --legacy-peer-deps`, `tsc --noEmit`, `npm run lint`, `jest --ci` and `next build`. It also fails when a dependency manifest changed vs the base, because only W0-TH may add dependencies (`ALLOW_DEPS=1` acknowledges an approved change). `WP_ID` names the docker resources (default: from the branch name). Several WPs can run it at the same time.

## Docker images

| Service | Base image |
|---------|------------|
| backend | `python:3.12-slim-bookworm` (hash-locked `pip install --require-hashes`, wheels only) |
| mcp-server | `python:3.12-slim-bookworm` (same) |
| frontend | `node:22-alpine` (build uses `npm ci --legacy-peer-deps`) |
| proxy | `nginx:1.28-alpine` |
| ollama (optional profile) | `ollama/ollama` pinned to a specific version tag |

Shell scripts must keep LF line endings (enforced by `.gitattributes`) and `backend/entrypoint.sh` must be committed executable.
