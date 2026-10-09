# Architecture

## System Overview

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Frontend       │────▶│   Backend        │────▶│   PostgreSQL     │
│   Next.js 14     │     │   Flask 3.0      │     │   + pgcrypto     │
│   Port 3000      │     │   Port 5000      │     │   Port 5432      │
└──────────────────┘     └────────┬─────────┘     └──────────────────┘
                                  │
                         ┌────────▼─────────┐
                         │   Redis 7        │
                         │   Cache/Queue    │
                         │   Port 6379      │
                         └──────────────────┘
```

- **Frontend → Backend**: REST API (`/api/v1/*`) + Socket.IO WebSocket
- **Backend → PostgreSQL**: SQLAlchemy ORM with Alembic migrations
- **Backend → Redis**: JWT blocklist, rate limiter storage, Socket.IO message queue
- **Backend → External**: S3 (artifact storage), OpenAI/Gemini (AI reports), Slack (webhooks)

---

## Tech Stack

### Backend
| Component         | Technology                                     |
|-------------------|------------------------------------------------|
| Framework         | Flask 3.0 + Eventlet (async)                   |
| ORM               | SQLAlchemy 2.x + Flask-Migrate (Alembic)       |
| Authentication    | Flask-JWT-Extended (access + refresh tokens)    |
| Real-time         | Flask-SocketIO with Redis message queue         |
| Rate Limiting     | Flask-Limiter (200/day, 50/hour default)        |
| Encryption        | cryptography (Fernet symmetric)                 |
| Password Hashing  | bcrypt (12 rounds)                              |
| AI Providers      | OpenAI GPT-4, Google Gemini Pro                 |
| PDF Generation    | WeasyPrint                                      |
| Data Import       | pandas (Excel/CSV parsing)                      |
| Object Storage    | boto3 (S3-compatible)                           |

### Frontend
| Component         | Technology                                     |
|-------------------|------------------------------------------------|
| Framework         | Next.js 14 (App Router)                        |
| Language          | TypeScript 5.3                                 |
| State Management  | Zustand 4.4                                    |
| Graph Viz         | @xyflow/react 12.10 (React Flow)               |
| UI Primitives     | Radix UI (Dialog, Select, Dropdown, Tabs, etc.)|
| Styling           | Tailwind CSS 3.3 + CSS custom properties       |
| Animations        | Framer Motion 12.31                            |
| Real-time         | socket.io-client 4.6                           |
| Forms             | react-hook-form 7.49 + Zod 3.22               |
| Icons             | Lucide React                                   |

### Infrastructure
| Component         | Technology                                     |
|-------------------|------------------------------------------------|
| Containerization  | Docker + Docker Compose                        |
| Database          | PostgreSQL 16 (uuid-ossp, pgcrypto extensions) |
| Cache/Queue       | Redis 7 Alpine                                 |

---

## Project Structure

```
SheetStorm/
├── docker-compose.yml                 # 4-service orchestration
├── start.sh                           # One-command startup script
│
├── backend/
│   ├── app/
│   │   ├── __init__.py                # Flask app factory, extensions
│   │   ├── config.py                  # Environment-based configuration
│   │   ├── seed.py                    # Database seeding (org + admin user)
│   │   ├── models/                    # 16 SQLAlchemy model files (24+ tables)
│   │   ├── schemas/                   # Marshmallow/Pydantic schemas
│   │   ├── services/                  # 8 business logic services
│   │   │   ├── ai_service.py          # OpenAI/Gemini summary generation
│   │   │   ├── encryption_service.py  # Fernet encrypt/decrypt
│   │   │   ├── hash_service.py        # MD5/SHA256/SHA512 computation
│   │   │   ├── storage_service.py     # S3/local file storage
│   │   │   ├── chain_of_custody_service.py  # Forensic evidence trail
│   │   │   ├── notification_service.py      # In-app + WebSocket + Slack
│   │   │   ├── import_service.py      # Excel/CSV import
│   │   │   └── graph_automation_service.py  # Attack graph generation
│   │   ├── api/v1/endpoints/          # 17 endpoint modules
│   │   ├── api/websocket/             # Socket.IO event handlers
│   │   └── middleware/                # RBAC, audit logging, sanitization
│   ├── migrations/                    # Alembic migration chain
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/                       # Next.js 14 App Router pages
│   │   ├── components/                # UI, layout, providers, incidents, graph
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── lib/                       # API client, stores, design tokens
│   │   └── types/                     # TypeScript interfaces
│   ├── package.json
│   └── Dockerfile
│
├── database/
│   └── init/                          # SQL schema + role seeds
│
├── assets/
│   └── docs/                          # Technical documentation
└── IRSpreadsheet/                     # Sample IR data (HTML)
```

---

## RBAC

Authorization is **permission-driven and tenant-scoped**. No decision depends on a role's name.

- **Catalog**: `backend/app/permissions.py` lists every permission key with its group, label,
  description and flags (`dangerous`, `privileged`, `api_key_grantable`, `platform_only`).
  `GET /api/v1/permissions` serves it, so the UI and the backend always agree. A test fails when
  code enforces a key that is not in the catalog, or checks a role name.
- **Roles**: the six system roles (Administrator, Incident Responder, Analyst, Manager, Operator,
  Viewer) are global and immutable; clone one to customise it. Custom roles belong to one
  organization (`roles.organization_id`); names are unique per org (case-insensitive) and cannot
  shadow a system name. Lookups go through `Role.visible_to(org)` / `Role.resolve(name, org)`,
  so another tenant's role id answers 404.
- **Additive rule**: a user's permissions are the union over all of their roles (only system
  roles and roles of their own org count). No role ever restricts another: to restrict a user,
  remove a role.
- **Incident visibility** (`middleware/rbac.py::accessible_incidents_query`, the single source):
  directly assigned incidents, plus the union of the scopes the user holds:
  `incidents:read_all` (every incident in the org), `incidents:read_team` (incidents of the
  user's teams and incidents not restricted to a team), `incidents:read_tlp_white`
  (every TLP:WHITE incident). A Viewer+Analyst therefore sees team scope + TLP:WHITE.
- **Guardrails** (`services/rbac_guard.py`), enforced on every role and user mutation:
  - nobody grants a permission they lack (`403 privilege_escalation {missing}`), including via
    role create/edit/clone, role assignment, user creation and Supabase sync;
  - nobody acts on a user holding permissions they lack (`403 insufficient_privilege`);
  - an organization never loses its last active administrator (`users:manage` + `roles:manage`;
    `409 last_admin`, serialised with a row lock on the organization);
  - an admin never strips their own admin permissions (`409 self_lockout`), never disables or
    deletes themselves (`400 self_action`) and changes their own password only through
    `/auth/change-password` (`400 use_change_password`).
  Denials are recorded as `privilege_escalation_blocked` / `last_admin_blocked` security events.
- **Platform admin**: `system:manage` is only effective for members of the platform
  organization (`PLATFORM_ORG_SLUG`, default `default`).
- **Grants**: new permission keys and their role grants are registered once, in the catalog and
  in the `admin_guardrails_rbac` data migration. Feature migrations never `UPDATE roles`.

---

## Design System

The **Cyber-Noir** design system uses CSS custom properties with glassmorphism effects.

- **Color Palette**: Deep navy backgrounds (`#0f172a`), electric cyan accents (`#06b6d4`)
- **Themes**: Light + dark mode
- **Key Utilities**: `.glass`, `.glass-hover`, `.glass-card`, `.gradient-primary`
- **Design Tokens**: Centralized in `frontend/src/lib/design-tokens.ts`
