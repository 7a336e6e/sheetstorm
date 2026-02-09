# SheetStorm — Copilot Instructions

## Skills
Skill descriptions and requirements for effective Copilot usage in this project are found in the ./github/skills directory. Each skill file includes a description, example prompts, and best practices for leveraging Copilot to assist with that aspect of the codebase.

## Architecture

Four Docker services: **Next.js 14 frontend** (:3000) → **Flask 3.0 backend** (:5000) → **PostgreSQL** (:5432) + **Redis** (:6379). Communication is REST (`/api/v1/*`) + Socket.IO WebSocket. Redis handles JWT blocklist, rate limiter storage, and SocketIO message queue for scaling. Run everything with `./start.sh` (builds, migrates, seeds automatically).

## Backend Conventions

- **Single shared blueprint** — all endpoints decorate on `api_v1` imported from `app.api.v1`. Endpoint files are side-effect imported at bottom of `app/api/v1/__init__.py`.
- **Decorator stack**: `@api_v1.route` → `@jwt_required()` → `@require_permission('entity:action')` → optional `@limiter.limit()`.
- **Models** extend `BaseModel` (`app/models/base.py`) which provides `id` (UUID v4), `created_at`, `updated_at`, `created_by`, `updated_by`, `is_deleted`. Table names are plural snake_case (`compromised_hosts`), classes are singular PascalCase (`CompromisedHost`).
- **Responses**: return `jsonify(dict)` directly with HTTP status codes. Pagination: `{'items': [...], 'total': N, 'page': P, 'per_page': PP}`. Errors: `{'error': 'message'}`.
- **Config**: class inheritance in `app/config.py` — `BaseConfig` → `DevelopmentConfig`/`ProductionConfig`. All secrets from `os.getenv()` with dev fallbacks.
- **Migrations**: Flask-Migrate (Alembic). Run inside container: `docker compose exec backend flask db upgrade`. Migration files use descriptive names, not auto-hashes.
- **Services** in `app/services/` encapsulate business logic (AI, encryption, hashing, graph automation, storage, notifications). Endpoints should be thin controllers delegating to services.

## Frontend Conventions

- **Next.js App Router** — pages in `src/app/`, layouts via `layout.tsx`. Dashboard routes live under `/dashboard/*`, auth pages (`/login`, `/register`) are outside dashboard layout.
- **Design system**: glassmorphism theme using `design-tokens.ts` — all colors are Tailwind class strings, not CSS variables. Token maps use `as const` for type inference. Severity/status/phase tokens map to specific color classes.
- **UI components** follow shadcn/ui pattern: `React.forwardRef`, `className` prop merged via `cn()` from `@/lib/utils`, variants via `cva` (class-variance-authority). 17 primitives in `components/ui/`. Radix UI for accessible primitives (Dialog, Select, Tabs, Switch, DropdownMenu).
- **State**: Zustand stores in `lib/store.ts` (auth + incidents) and `lib/feature-stores.ts` (notifications, timeline, hosts, tasks, artifacts, graph). Auth store uses `persist` middleware. Feature stores follow a generic `createEntityStore` pattern with loading/error states and CRUD methods.
- **API client**: singleton `ApiClient` in `lib/api.ts`. Token stored in `localStorage` as `access_token`. Auto-redirects to `/login` on 401. Built-in retry (2 attempts) with exponential backoff for 5xx/network errors. Typed methods: `get<T>`, `post<T>`, `put<T>`, `patch<T>`, `delete<T>`.
- **WebSocket**: `SocketProvider` in `components/providers/` connects when authenticated. Custom hooks: `useSocket()` for raw access, `useSocketEvent(event, handler)` for subscriptions, `useSocketEmit()` for sending, `useIncidentRoom(id)` for joining/leaving incident collaboration rooms. Token passed as `auth.token` param.
- **Validation**: Zod schemas in `lib/validations.ts`. Use `validate(schema, data)` helper which returns `{success, data, errors}`.
- **Icons**: Lucide React exclusively — never inline SVGs.

## Key Patterns

- **RBAC permissions** use `entity:action` format (`incidents:read`, `artifacts:write`). Check via `require_permission()` decorator (backend) or `useAuthStore().hasPermission()` (frontend).
- **Multi-tenancy**: most entities have `organization_id` FK with `ON DELETE CASCADE`. Users belong to organizations via the `organization_id` column.
- **IR lifecycle phases** (1–6): Preparation → Identification → Containment → Eradication → Recovery → Lessons Learned. Phase tokens in `design-tokens.ts`.
- **Real-time updates**: backend emits SocketIO events → frontend `useSocketEvent` handlers push into Zustand stores or local state. Redis is the SocketIO message queue.
- **Types**: all shared interfaces in `frontend/src/types/index.ts`. Backend returns snake_case JSON; frontend types use snake_case to match.

## Development Workflow

```bash
./start.sh                              # Build + start all services + migrate + seed
docker compose logs -f backend          # Tail backend logs
docker compose exec backend flask db upgrade  # Run migrations
docker compose exec backend python -c "from app.seed import seed_all; seed_all()"  # Re-seed
docker compose up --build backend       # Rebuild single service
```

Default admin: `admin@sheetstorm.local` / value of `ADMIN_PASSWORD` in `.env` (default `changeme`).
