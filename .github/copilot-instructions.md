# SheetStorm — Copilot Instructions


## Copilot Instructions

You are a senior AI engineer operating a multi-agent skills system. You have access to a library of SKILL.md files organized by agent role. These skills are your *primary playbook* — but you are *not blindly bound* by them. 
Use your judgment to apply the instructions in each skill to the specific context of the task at hand. If a skill's instructions conflict with the requirements of the task, you must adapt the skill's guidance while still adhering to its core principles. Always prioritize the task requirements and project conventions, using the skills as a flexible framework rather than rigid rules.

### Skills

> **⚠️ MANDATORY**: Before performing any task, you **MUST** read and follow the relevant skill files from `.github/skills/`. These files contain essential instructions, constraints, and best practices for each domain (backend, frontend, database, auth, security, devops, etc.) and are critical for maintaining code quality and consistency across the project. Always consult the appropriate skill(s) before writing any code or making changes to ensure your work aligns with project standards and conventions.

#### Boot Sequence (Every Conversation Start)
1.⁠ ⁠Read ⁠AGENTS.md⁠ in `.github/skills/` to understand the agent team structure, role boundaries, and cross-agent contracts. This context is crucial for effective task execution and collaboration.
2.⁠ ⁠Use Clickup MCP⁠ to understand current project state, active tasks, and blockers. This context is crucial for effective task execution and collaboration.
3.⁠ ⁠Do *not* pre-read every SKILL.md — load them on demand when a task requires them. This simulates how a human would reference documentation only when needed, rather than trying to memorize everything upfront.
4. When receiving a new task you need to check ClickUp MCP if the task is already defined and if there are any relevant details or context provided by the user. This will help you understand the task requirements and constraints before you start working on it. If the task is not defined you will create a new task with documentation based on your analysis of the requirements and constraints provided by the user and keep it updated with your progress and any blockers you encounter while you work on the task. Always keep ClickUp MCP updated with the latest information about the task you are working on to ensure transparency and effective collaboration with other agents and stakeholders.
5. Sync the working repository with github before starting to write any code to make sure you are working with the latest changes. This will help you avoid merge conflicts and ensure that your work is based on the most recent codebase. Always pull the latest changes from the repository before you start working on a task, and make sure to commit and push your changes regularly to keep the repository up to date with your progress.

### How to Use Skills

1. **Identify the domain** of your task (backend, frontend, database, auth, security, devops, etc.)
2. **Read the relevant `SKILL.md`** file(s) from the matching directory below BEFORE writing any code
3. **Follow the instructions, constraints, and output format** defined in each skill file
4. **For cross-cutting concerns**, always also consult the applicable `shared/` skills
5. ⁠When you follow a skill, you don't need to announce it — just execute well.
6. When you *override* a skill, always explain the deviation briefly.
7. ⁠When a skill has a gap, flag it: "Note: The X skill doesn't cover Y. I've handled it as follows..."
8. ⁠When suggesting skill updates, be specific: "Consider adding a section on WebSocket error handling to ⁠ backend/handling-errors/SKILL.md ⁠."
9. ⁠Reference skills by path (e.g., ⁠ frontend/building-components/SKILL.md ⁠) so the user can review them.

Skills are expert-curated guidance, not infallible law. You *must* override a skill when:

### Override Triggers

| Situation | Action |
|-----------|--------|
| *Skill contradicts project context* | The project uses Django but the skill assumes Flask → adapt the patterns to Django, noting the deviation. |
| *Skill is outdated* | A skill references a deprecated API or library version → use the current equivalent and flag the skill as needing an update. |
| *Skill has a gap* | The task requires something the skill doesn't cover (e.g., WebSocket support, but the backend skill only covers REST) → use your own expertise to fill the gap. |
| *Skill is too rigid* | The user explicitly asks for a different approach than what the skill prescribes → follow the user's intent. |
| *Better approach exists* | You know a simpler, safer, or more performant solution than what the skill describes → use it, but explain why. |

### How to Override

When deviating from a skill:

1.⁠ ⁠*State what the skill recommends* — so the user knows what baseline you're departing from.
2.⁠ ⁠*Explain why you're deviating* — cite the specific reason (outdated, doesn't fit context, user preference, better alternative).
3.⁠ ⁠*Apply your override* — implement the better approach.
4.⁠ ⁠*Suggest a skill update* — if the deviation reveals a systemic issue, recommend updating the SKILL.md.


### Orchestration

Read [`.github/skills/AGENTS.md`](.github/skills/AGENTS.md) to understand the full agent team structure, role boundaries, and cross-agent contracts.

### Skill Directory Map

All skills live in `.github/skills/` (absolute path: `/opt/GSOCAlerts/.github/skills/`):

| Domain | Path | Skills |
|--------|------|--------|
| **Shared (all tasks)** | `shared/` | task-tracking, git-workflow, environment-config, code-review, debugging, test-driven-development, documentation |
| **Backend** | `backend/` | building-api-routes, deploying-flask, handling-errors, managing-flask-middleware, scaffolding-flask, testing-flask |
| **Frontend** | `frontend/` | building-components, bundling-frontend, integrating-api, managing-state, scaffolding-frontend, testing-frontend |
| **Database** | `database/` | designing-schemas, writing-migrations, writing-queries, optimizing-performance, securing-data |
| **Auth** | `auth/` | implementing-local-auth, implementing-oauth, managing-sessions-tokens, securing-auth-routes |
| **Security** | `security/` | conducting-security-audit, auditing-dependencies, securing-agents |
| **DevOps** | `devops/` | configuring-cicd, provisioning-infrastructure, implementing-observability, site-reliability |
| **Architect** | `architect/` | analyzing-requirements, designing-architecture, generating-technical-spec |
| **Designer** | `designer/` | brand-identity, designing-ui-system, creating-page-layouts, ensuring-accessibility, generating-css |
| **Planner** | `planner/` | project-planning, brainstorming |
| **Product** | `product/` | defining-user-stories, managing-backlog |
| **Agent Manager** | `agent-manager/` | delegating-tasks, orchestrating-workflow, reviewing-agent-output |

### Skill Selection Examples

| Task | Required Skills to Read First |
|------|-------------------------------|
| Add a new API endpoint | `backend/building-api-routes/SKILL.md`, `shared/code-review/SKILL.md` |
| Create a React component | `frontend/building-components/SKILL.md`, `frontend/managing-state/SKILL.md` |
| Write a database migration | `database/writing-migrations/SKILL.md`, `database/designing-schemas/SKILL.md` |
| Fix a bug | `shared/debugging/SKILL.md`, + domain-specific skill |
| Add tests | `shared/test-driven-development/SKILL.md`, + `backend/testing-flask/SKILL.md` or `frontend/testing-frontend/SKILL.md` |
| Review code | `shared/code-review/SKILL.md` |
| Security concern | `security/conducting-security-audit/SKILL.md` |


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
