# Development Guide

## Docker Setup (Recommended)

```bash
git clone <repo-url> && cd SheetStorm
chmod +x start.sh && ./start.sh
```

This auto-generates secrets, builds all 4 containers, runs migrations, and seeds the admin user.

## Manual Setup

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

## Production WSGI

```bash
gunicorn --worker-class eventlet -w 1 wsgi:app
```

## Testing

> ⚠️ Test suites are not yet implemented.

**Planned Stack**:
- Backend: pytest + pytest-flask + factory_boy
- Frontend: Vitest + @testing-library/react + MSW
- E2E: Playwright
