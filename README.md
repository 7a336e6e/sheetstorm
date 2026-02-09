# SheetStorm ⚡

**Kill the Spreadsheet of Doom.** A full-stack, multi-tenant incident response platform that replaces the infamous IR spreadsheet with attack graph visualization, MITRE ATT&CK mapping, AI-powered reporting, and real-time collaboration.

> *Because your incident response workflow deserves better than a shared Excel file.*

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [WebSocket Events](#websocket-events)
- [Design System](#design-system)
- [Database Schema](#database-schema)
- [Development](#development)
- [Testing](#testing)
- [Known Issues & Limitations](#known-issues--limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

SheetStorm provides a complete Incident Response (IR) lifecycle pipeline:

1. **Preparation** — Define teams, roles, integrations
2. **Identification** — Create incidents, import evidence from Excel/CSV
3. **Containment** — Track compromised hosts, accounts, IOCs
4. **Eradication** — Map attack paths, identify malware/tools
5. **Recovery** — Monitor remediation tasks, verify artifacts
6. **Lessons Learned** — Generate AI summaries and PDF reports

The platform supports 6 RBAC roles with 40+ granular permissions, multi-organization tenancy, and real-time collaboration via WebSocket.

---

## Architecture

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
| Security Headers  | Flask-Talisman                                  |
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

## Features

### Core IR Workflow
- **Incident Management** — Full CRUD with severity, status, phase tracking, and auto-incrementing incident numbers per org
- **Timeline Events** — Chronological event tracking with MITRE ATT&CK tactic/technique mapping (14 tactics, 200+ techniques)
- **Compromised Hosts** — Host tracking with containment status, system type inference, IP/MAC addresses
- **Compromised Accounts** — Account tracking with Fernet-encrypted password storage and controlled reveal
- **Network IOCs** — Protocol, port, DNS/IP tracking with direction and threat intel source
- **Host-Based IOCs** — Artifact types (WMI, ASEP, registry, scheduled tasks, services, files, processes)
- **Malware & Tools** — File hashes (MD5/SHA256/SHA512), malware families, sandbox report links

### Attack Graph Visualization
- **Auto-Generation** — Creates graph from incident data: host nodes → linked sub-nodes (accounts, malware, host IOCs) → network IOC nodes → lateral movement edges
- **Manual Editing** — Add/edit/delete nodes and edges, draw-mode for edge linking
- **11 Custom Node Types** — Host, DC, Attacker, C2, Account, IP, Malware, Host Indicator, Cloud, Database, Default
- **12 Edge Types** — Lateral movement, credential theft, C2, initial access, privilege escalation, etc.
- **Interactive** — Drag-to-reposition (persisted), auto-layout, minimap, PNG export, legend panel

### Evidence & Reporting
- **Artifacts** — Upload with triple-hash (MD5/SHA256/SHA512) integrity, chain of custody tracking, S3 or local storage
- **Reports** — PDF generation via WeasyPrint, AI-powered summaries (executive, technical, recommendations)
- **Audit Logging** — Full action trail with IP address, user agent, request details

### Collaboration & Auth
- **RBAC** — 6 system roles: Administrator, Incident Responder, Analyst, Manager, Operator, Viewer
- **Multi-Tenant** — Organization-scoped data isolation with assignment-based access for limited roles
- **WebSocket** — Real-time presence, cursor tracking, typing indicators, graph node sync, notifications
- **Data Import** — Multi-step Excel import wizard with column mapping and preview

### Design System
- **Cyber-Noir Theme** — Glassmorphism aesthetic with deep navy backgrounds and cyan accents
- **Dual Theme** — Light and dark mode with CSS custom properties
- **16 UI Components** — Button, Card, Input, Badge, Dialog, Select, Table, Tabs, Skeleton, Switch, Dropdown, Toast, etc.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- (Optional) Python 3.11+ and Node.js 18+ for local development

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repo-url> && cd SheetStorm

# Start everything (generates secrets, builds containers, runs migrations, seeds data)
chmod +x start.sh && ./start.sh
```

This will:
1. Generate `SECRET_KEY`, `JWT_SECRET_KEY`, and `FERNET_KEY` if not set
2. Build and start all 4 containers (database, redis, backend, frontend)
3. Run Alembic migrations
4. Seed the default organization and admin user

### Access Points
| Service  | URL                                |
|----------|------------------------------------|
| Frontend | http://127.0.0.1:3000              |
| Backend  | http://127.0.0.1:5000/api/v1       |
| Database | postgresql://localhost:5432        |
| Redis    | redis://localhost:6379             |

### Default Admin Credentials
- **Email**: `admin@sheetstorm.local` (or `ADMIN_EMAIL` env var)
- **Password**: Check `ADMIN_PASSWORD` in `.env`

### Manual Setup (Development)

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
flask db upgrade
python -c "from app.seed import seed_all; seed_all()"
flask run --debug

# Frontend
cd frontend
npm install
npm run dev
```

---

## Environment Variables

| Variable                  | Required | Default                           | Description                           |
|---------------------------|----------|-----------------------------------|---------------------------------------|
| `SECRET_KEY`              | Yes      | —                                 | Flask secret key (auto-generated)     |
| `JWT_SECRET_KEY`          | Yes      | —                                 | JWT signing key (auto-generated)      |
| `FERNET_KEY`              | Yes      | —                                 | Fernet encryption key (auto-generated)|
| `DATABASE_URL`            | Yes      | `postgresql://sheetstorm:changeme@localhost:5432/sheetstorm` | PostgreSQL connection |
| `REDIS_URL`               | Yes      | `redis://localhost:6379/0`        | Redis connection                      |
| `FLASK_ENV`               | No       | `production`                      | `development` or `production`         |
| `POSTGRES_USER`           | No       | `sheetstorm`                       | PostgreSQL user                       |
| `POSTGRES_PASSWORD`       | No       | `changeme`                        | PostgreSQL password                   |
| `POSTGRES_DB`             | No       | `sheetstorm`                       | PostgreSQL database name              |
| `ADMIN_EMAIL`             | No       | `admin@sheetstorm.local`           | Default admin user email              |
| `ADMIN_PASSWORD`          | No       | `ChangeMe123!`                    | Default admin user password           |
| `OPENAI_API_KEY`          | No       | —                                 | OpenAI API key for AI reports         |
| `GOOGLE_AI_API_KEY`       | No       | —                                 | Google Gemini API key                 |
| `S3_ENDPOINT`             | No       | —                                 | S3-compatible endpoint URL            |
| `S3_ACCESS_KEY`           | No       | —                                 | S3 access key                         |
| `S3_SECRET_KEY`           | No       | —                                 | S3 secret key                         |
| `S3_BUCKET`               | No       | `sheetstorm-artifacts`             | S3 bucket name                        |
| `S3_REGION`               | No       | `us-east-1`                       | S3 region                             |
| `SLACK_WEBHOOK_URL`       | No       | —                                 | Slack webhook for notifications       |
| `SUPABASE_URL`            | No       | —                                 | Supabase URL for SSO                  |
| `SUPABASE_ANON_KEY`       | No       | —                                 | Supabase anonymous key                |
| `NEXT_PUBLIC_API_URL`     | No       | `http://127.0.0.1:5000/api/v1`   | Backend API URL for frontend          |
| `NEXT_PUBLIC_WS_URL`      | No       | `http://127.0.0.1:5000`          | WebSocket URL for frontend            |

---

## Project Structure

```
SheetStorm/
├── README.md                          # This file
├── tech-spec.md                       # Technical specification
├── tasks.md                           # JIRA-level task tracker
├── docker-compose.yml                 # 4-service orchestration
├── start.sh                           # One-command startup script
│
├── backend/
│   ├── app/
│   │   ├── __init__.py                # Flask app factory, extensions
│   │   ├── config.py                  # Environment-based configuration
│   │   ├── seed.py                    # Database seeding (org + admin user)
│   │   ├── models/                    # 16 SQLAlchemy model files (24+ tables)
│   │   │   ├── base.py               # BaseModel (UUID PK, created_at, to_dict)
│   │   │   ├── user.py               # User, Role, UserRole, Session, PasswordHistory
│   │   │   ├── organization.py        # Organization (multi-tenant)
│   │   │   ├── incident.py           # Incident, IncidentAssignment
│   │   │   ├── timeline.py           # TimelineEvent (MITRE ATT&CK dictionaries)
│   │   │   ├── compromised.py        # CompromisedHost, CompromisedAccount
│   │   │   ├── ioc.py                # NetworkIndicator, HostBasedIndicator, MalwareTool
│   │   │   ├── attack_graph.py       # AttackGraphNode (16 types), AttackGraphEdge (12 types)
│   │   │   ├── artifact.py           # Artifact, ChainOfCustody
│   │   │   ├── task.py               # Task, TaskComment
│   │   │   ├── report.py             # Report (PDF/AI)
│   │   │   ├── notification.py       # Notification
│   │   │   ├── audit.py              # AuditLog
│   │   │   ├── integration.py        # Integration (S3, Slack, AI configs)
│   │   │   └── team.py               # Team, TeamMember
│   │   ├── schemas/                   # Marshmallow/Pydantic schemas
│   │   ├── services/                  # 8 business logic services
│   │   │   ├── ai_service.py          # OpenAI/Gemini summary generation
│   │   │   ├── encryption_service.py  # Fernet encrypt/decrypt (singleton)
│   │   │   ├── hash_service.py        # MD5/SHA256/SHA512 computation
│   │   │   ├── storage_service.py     # S3/local file storage
│   │   │   ├── chain_of_custody_service.py  # Forensic evidence trail
│   │   │   ├── notification_service.py      # In-app + WebSocket + Slack
│   │   │   ├── import_service.py      # Excel/CSV import with pandas
│   │   │   └── graph_automation_service.py  # Attack graph event processing
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py        # Blueprint registration
│   │   │   │   └── endpoints/         # 17 endpoint modules
│   │   │   │       ├── auth.py        # Login, register, logout, refresh, me
│   │   │   │       ├── users.py       # User CRUD + role management
│   │   │   │       ├── incidents.py   # Incident CRUD + import wizard
│   │   │   │       ├── timeline.py    # Timeline events + MITRE reference data
│   │   │   │       ├── compromised.py # Hosts + accounts (encrypted passwords)
│   │   │   │       ├── iocs.py        # Network, host-based, malware IOCs
│   │   │   │       ├── attack_graph.py # Graph CRUD + auto-generation
│   │   │   │       ├── artifacts.py   # Upload, download, verify, custody
│   │   │   │       ├── tasks.py       # Tasks + comments
│   │   │   │       ├── reports.py     # PDF generation + AI summaries
│   │   │   │       ├── notifications.py # List, read, mark-all
│   │   │   │       ├── audit.py       # Audit log queries + stats
│   │   │   │       ├── integrations.py # Integration CRUD
│   │   │   │       ├── teams.py       # Team CRUD + membership
│   │   │   │       ├── organization.py # Organization management
│   │   │   │       └── health.py      # Health check endpoints
│   │   │   └── websocket/
│   │   │       └── __init__.py        # Socket.IO event handlers
│   │   └── middleware/
│   │       ├── rbac.py                # Permission/role/incident access decorators
│   │       └── audit.py               # Audit logging decorator + helpers
│   ├── migrations/                    # Alembic migration chain
│   ├── tests/                         # Test directory (empty)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/                       # Next.js 14 App Router pages
│   │   │   ├── page.tsx               # Landing page
│   │   │   ├── login/page.tsx         # Authentication
│   │   │   ├── register/page.tsx      # Registration
│   │   │   └── dashboard/
│   │   │       ├── page.tsx           # Dashboard home
│   │   │       ├── incidents/         # List, new, detail (10 tabs)
│   │   │       ├── reports/           # Report generation
│   │   │       ├── activity/          # Audit log viewer
│   │   │       └── admin/             # Users, teams, settings
│   │   ├── components/
│   │   │   ├── attack-graph/          # React Flow viewer + custom nodes/edges
│   │   │   ├── incidents/             # Sub-tab components (events, hosts, accounts, IOCs, etc.)
│   │   │   ├── layout/               # Sidebar, header
│   │   │   ├── providers/            # Auth guard, theme provider, socket provider
│   │   │   ├── ui/                   # 16 reusable UI components
│   │   │   └── users/                # User management modals
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── lib/
│   │   │   ├── api.ts                 # API client with token management
│   │   │   ├── store.ts              # Zustand stores (auth, incidents)
│   │   │   ├── utils.ts              # Utility functions
│   │   │   └── design-tokens.ts      # Theme color constants
│   │   └── types/
│   │       └── index.ts              # TypeScript interfaces for all entities
│   ├── package.json
│   └── Dockerfile
│
├── database/
│   ├── init/
│   │   ├── 001_extensions.sql         # uuid-ossp, pgcrypto
│   │   ├── 002_schema.sql            # 23 tables with triggers and indexes
│   │   └── 003_seed_roles.sql        # 6 system roles with permissions
│   └── Dockerfile
│
├── IRSpreadsheet/                     # Sample IR data (HTML format)
└── scripts/                          # Utility scripts
```

---

## API Reference

All endpoints are prefixed with `/api/v1`. Authentication via `Authorization: Bearer <token>` header.

### Authentication
| Method | Endpoint           | Description          | Rate Limit |
|--------|--------------------|----------------------|------------|
| POST   | `/auth/register`   | Register new user    | 3/hour     |
| POST   | `/auth/login`      | Login                | 5/minute   |
| POST   | `/auth/logout`     | Logout (revoke JWT)  | —          |
| POST   | `/auth/refresh`    | Refresh access token | —          |
| GET    | `/auth/me`         | Current user info    | —          |
| PUT    | `/auth/password`   | Change password      | —          |

### Incidents
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents`                              | List incidents (paginated)     |
| POST   | `/incidents`                              | Create incident                |
| GET    | `/incidents/{id}`                         | Get incident details           |
| PUT    | `/incidents/{id}`                         | Update incident                |
| DELETE | `/incidents/{id}`                         | Delete incident                |
| PATCH  | `/incidents/{id}/status`                  | Update status/phase            |
| POST   | `/incidents/{id}/import/parse`            | Parse Excel file               |
| POST   | `/incidents/{id}/import/submit`           | Submit mapped import data      |

### Timeline Events
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/timeline`                | List timeline events           |
| POST   | `/incidents/{id}/timeline`                | Create event                   |
| PUT    | `/incidents/{id}/timeline/{eid}`          | Update event                   |
| DELETE | `/incidents/{id}/timeline/{eid}`          | Delete event                   |
| POST   | `/incidents/{id}/timeline/{eid}/mark-ioc` | Flag event as IOC              |
| GET    | `/mitre/tactics`                          | List MITRE tactics             |
| GET    | `/mitre/techniques/{tactic}`              | List techniques for tactic     |

### Compromised Assets
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/hosts`                   | List compromised hosts         |
| POST   | `/incidents/{id}/hosts`                   | Add compromised host           |
| PUT    | `/incidents/{id}/hosts/{hid}`             | Update host                    |
| DELETE | `/incidents/{id}/hosts/{hid}`             | Delete host                    |
| GET    | `/incidents/{id}/accounts`                | List compromised accounts      |
| POST   | `/incidents/{id}/accounts`                | Add account (password encrypted)|
| PUT    | `/incidents/{id}/accounts/{aid}`          | Update account                 |
| DELETE | `/incidents/{id}/accounts/{aid}`          | Delete account                 |
| GET    | `/incidents/{id}/accounts/{aid}/reveal`   | Reveal decrypted password      |

### IOCs
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/network-iocs`            | List network indicators        |
| POST   | `/incidents/{id}/network-iocs`            | Add network IOC                |
| PUT    | `/incidents/{id}/network-iocs/{nid}`      | Update network IOC             |
| DELETE | `/incidents/{id}/network-iocs/{nid}`      | Delete network IOC             |
| GET    | `/incidents/{id}/host-iocs`               | List host-based indicators     |
| POST   | `/incidents/{id}/host-iocs`               | Add host IOC                   |
| PUT    | `/incidents/{id}/host-iocs/{hid}`         | Update host IOC                |
| DELETE | `/incidents/{id}/host-iocs/{hid}`         | Delete host IOC                |
| GET    | `/incidents/{id}/malware`                 | List malware/tools             |
| POST   | `/incidents/{id}/malware`                 | Add malware entry              |
| PUT    | `/incidents/{id}/malware/{mid}`           | Update malware entry           |
| DELETE | `/incidents/{id}/malware/{mid}`           | Delete malware entry           |

### Attack Graph
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/attack-graph`            | Full graph with correlations   |
| POST   | `/incidents/{id}/attack-graph/auto-generate` | Auto-generate from data     |
| GET    | `/incidents/{id}/attack-graph/nodes`      | List nodes                     |
| POST   | `/incidents/{id}/attack-graph/nodes`      | Create node                    |
| PUT    | `/incidents/{id}/attack-graph/nodes/{nid}`| Update node                    |
| DELETE | `/incidents/{id}/attack-graph/nodes/{nid}`| Delete node                    |
| GET    | `/incidents/{id}/attack-graph/edges`      | List edges                     |
| POST   | `/incidents/{id}/attack-graph/edges`      | Create edge                    |
| PUT    | `/incidents/{id}/attack-graph/edges/{eid}`| Update edge                    |
| DELETE | `/incidents/{id}/attack-graph/edges/{eid}`| Delete edge                    |
| GET    | `/attack-graph/node-types`                | Available node types           |
| GET    | `/attack-graph/edge-types`                | Available edge types           |

### Artifacts & Evidence
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/artifacts`               | List artifacts                 |
| POST   | `/incidents/{id}/artifacts`               | Upload artifact (multipart)    |
| GET    | `/incidents/{id}/artifacts/{aid}/download` | Download artifact             |
| POST   | `/incidents/{id}/artifacts/{aid}/verify`  | Verify integrity               |
| GET    | `/incidents/{id}/artifacts/{aid}/custody` | Chain of custody log           |

### Tasks
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/incidents/{id}/tasks`                   | List tasks                     |
| POST   | `/incidents/{id}/tasks`                   | Create task                    |
| PUT    | `/incidents/{id}/tasks/{tid}`             | Update task                    |
| DELETE | `/incidents/{id}/tasks/{tid}`             | Delete task                    |
| POST   | `/incidents/{id}/tasks/{tid}/comments`    | Add comment                    |
| GET    | `/incidents/{id}/tasks/{tid}/comments`    | List comments                  |

### Reports
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| POST   | `/incidents/{id}/reports/generate-pdf`    | Generate PDF report            |
| POST   | `/incidents/{id}/reports/ai-generate`     | Generate AI summary            |
| GET    | `/incidents/{id}/reports`                 | List reports                   |

### Admin & System
| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| GET    | `/users`                                  | List users                     |
| POST   | `/users`                                  | Create user                    |
| GET    | `/users/{id}`                             | Get user details               |
| PUT    | `/users/{id}`                             | Update user                    |
| DELETE | `/users/{id}`                             | Deactivate user                |
| GET    | `/users/{id}/roles`                       | Get user roles                 |
| POST   | `/users/{id}/roles`                       | Assign role                    |
| DELETE | `/users/{id}/roles/{rid}`                 | Remove role                    |
| GET    | `/roles`                                  | List roles                     |
| GET    | `/teams`                                  | List teams                     |
| POST   | `/teams`                                  | Create team                    |
| GET    | `/notifications`                          | List notifications             |
| PUT    | `/notifications/{id}/read`                | Mark as read                   |
| POST   | `/notifications/mark-all-read`            | Mark all as read               |
| GET    | `/audit-logs`                             | List audit logs (paginated)    |
| GET    | `/audit-logs/stats`                       | Audit statistics               |
| GET    | `/integrations`                           | List integrations              |
| POST   | `/integrations`                           | Create integration             |
| GET    | `/health`                                 | Health check                   |

---

## WebSocket Events

Connect via Socket.IO at `NEXT_PUBLIC_WS_URL` with `?token=<jwt>` query param.

### Client → Server
| Event              | Payload                                           | Description                |
|--------------------|---------------------------------------------------|----------------------------|
| `join_incident`    | `{ incident_id, user_id, user_name }`             | Join incident room         |
| `leave_incident`   | `{ incident_id }`                                 | Leave incident room        |
| `cursor_move`      | `{ incident_id, user_id, user_name, position }`   | Broadcast cursor position  |
| `typing_start`     | `{ incident_id, user_id, user_name, field }`       | Typing indicator on        |
| `typing_stop`      | `{ incident_id, user_id, field }`                  | Typing indicator off       |
| `graph_node_moved` | `{ incident_id, node_id, position, user_id }`      | Sync node position         |
| `ping`             | —                                                 | Keep-alive                 |

### Server → Client
| Event                  | Payload                                       | Description                |
|------------------------|-----------------------------------------------|----------------------------|
| `connected`            | `{ user_id, name }` or `{ anonymous: true }`  | Connection acknowledged    |
| `user_joined`          | `{ sid, user_id, name }`                       | User entered room          |
| `user_left`            | `{ sid }`                                      | User left room             |
| `users_in_room`        | `{ users: [...] }`                             | Current room roster        |
| `cursor_moved`         | `{ user_id, user_name, position }`             | Other user's cursor        |
| `user_typing`          | `{ user_id, user_name, field, typing }`        | Other user typing          |
| `graph_node_position`  | `{ node_id, position, user_id }`               | Other user moved node      |
| `notification`         | `Notification`                                 | Real-time notification     |
| `graph_node_added`     | `AttackGraphNode`                              | Node created via API       |
| `graph_node_updated`   | `AttackGraphNode`                              | Node updated via API       |
| `graph_node_deleted`   | `{ id }`                                       | Node deleted via API       |
| `graph_edge_added`     | `AttackGraphEdge`                              | Edge created via API       |
| `graph_edge_updated`   | `AttackGraphEdge`                              | Edge updated via API       |
| `graph_edge_deleted`   | `{ id }`                                       | Edge deleted via API       |
| `pong`                 | —                                              | Keep-alive response        |

---

## Design System

The "Cyber-Noir" design system uses CSS custom properties for theming with glassmorphism effects.

**Color Palette**: Deep navy backgrounds (`#0f172a`), electric cyan accents (`#06b6d4`), with light/dark mode support.

**Key Utilities**: `.glass`, `.glass-hover`, `.glass-card`, `.glass-border`, `.gradient-primary`, `.gradient-accent`.

**Design Tokens**: Centralized in `frontend/src/lib/design-tokens.ts` — severity colors, status colors, phase colors, node/edge type colors, badge variants.

---

## Database Schema

23 tables with UUID primary keys, automatic `updated_at` triggers, and auto-incrementing incident numbers per organization.

**Key Tables**: `users`, `roles`, `user_roles`, `organizations`, `incidents`, `incident_assignments`, `timeline_events`, `compromised_hosts`, `compromised_accounts`, `network_indicators`, `host_based_indicators`, `malware_tools`, `attack_graph_nodes`, `attack_graph_edges`, `artifacts`, `chain_of_custody`, `tasks`, `task_comments`, `reports`, `notifications`, `audit_logs`, `integrations`, `teams`, `team_members`.

**Extensions**: `uuid-ossp` (UUID generation), `pgcrypto` (cryptographic functions).

---

## Development

### Running Migrations

```bash
cd backend
flask db upgrade          # Apply all migrations
flask db migrate -m "..."  # Create new migration
flask db downgrade        # Rollback last migration
```

### WSGI Server

Production uses Eventlet via `wsgi.py`:
```bash
gunicorn --worker-class eventlet -w 1 wsgi:app
```

### Useful Commands

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

---

## Testing

> ⚠️ Test suites are not yet implemented. See `tasks.md` for the testing epic.

**Planned Stack**:
- Backend: pytest + pytest-flask + factory_boy
- Frontend: Vitest + @testing-library/react + MSW
- E2E: Playwright

---

## Project Status

**36 of 40 tasks completed** across 9 epics spanning 7 sprints. The 4 remaining tasks are deferred testing tasks.

### ✅ Completed
- **E1**: Critical bug fixes (6/6)
- **E2**: Attack graph auto-linking & deduplication (2/2)
- **E3**: WebSocket frontend integration — real-time presence, notifications, graph sync (3/3)
- **E4**: Missing frontend features — artifacts UI, reports, notifications panel, admin settings (7/7)
- **E5**: Code quality — custom hooks, error boundaries, Zod validation, feature stores, skeleton screens, mobile layout (8/8)
- **E7**: Security hardening — MFA/TOTP, SSO config, input sanitization, CSRF, rate limiting (5/5)
- **E8**: Backend documentation (1/1)
- **E9**: AI-powered reports (OpenAI/Gemini) & Google Drive integration (4/4)

### 🔜 Deferred
- **E6**: Testing — backend integration tests (pytest), frontend component tests (Vitest), E2E tests (Playwright), service unit tests — 0/4

---

## Roadmap

| Priority | Feature | Description |
|----------|---------|-------------|
| **P1** | Test suite | Backend pytest + frontend Vitest + Playwright E2E |
| **P1** | CI/CD pipeline | GitHub Actions for lint, test, build, deploy |
| **P2** | MITRE ATT&CK navigator overlay | Visual ATT&CK matrix heatmap from incident techniques |
| **P2** | Threat intel feed ingestion | Auto-enrich IOCs from STIX/TAXII, VirusTotal, AbuseIPDB |
| **P2** | Email notifications | SMTP integration for incident assignments and escalations |
| **P3** | RBAC policy engine | Custom permission sets beyond the 6 built-in roles |
| **P3** | Incident templates | Pre-configured incident types (ransomware, phishing, insider threat) |
| **P3** | Dashboard analytics | Charts for MTTR, incident volume trends, IOC frequency |
| **P3** | Export/import | STIX 2.1 bundle export, incident data export as JSON/CSV |

---

## Known Limitations

1. **No automated test coverage** — Test directories exist but suites are not yet implemented
2. **Single-worker deployment** — Eventlet requires `workers=1`; horizontal scaling via multiple containers + Redis queue
3. **WeasyPrint dependency** — PDF generation requires system-level Cairo/Pango libraries (included in Docker image)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
