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
├── docs/                              # Technical documentation
└── IRSpreadsheet/                     # Sample IR data (HTML)
```

---

## Design System

The **Cyber-Noir** design system uses CSS custom properties with glassmorphism effects.

- **Color Palette**: Deep navy backgrounds (`#0f172a`), electric cyan accents (`#06b6d4`)
- **Themes**: Light + dark mode
- **Key Utilities**: `.glass`, `.glass-hover`, `.glass-card`, `.gradient-primary`
- **Design Tokens**: Centralized in `frontend/src/lib/design-tokens.ts`
