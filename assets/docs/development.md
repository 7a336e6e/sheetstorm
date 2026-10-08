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

Tests must not need real secrets: the testing config uses throwaway keys. Never point tests at a production database.

### Frontend and E2E

> Not yet implemented. Planned stack: Vitest + @testing-library/react + MSW, and Playwright for E2E.

## Docker images

| Service | Base image |
|---------|------------|
| backend | `python:3.12-slim-bookworm` (hash-locked `pip install --require-hashes`, wheels only) |
| mcp-server | `python:3.12-slim-bookworm` (same) |
| frontend | `node:22-alpine` (build uses `npm ci --legacy-peer-deps`) |
| proxy | `nginx:1.28-alpine` |
| ollama (optional profile) | `ollama/ollama` pinned to a specific version tag |

Shell scripts must keep LF line endings (enforced by `.gitattributes`) and `backend/entrypoint.sh` must be committed executable.
