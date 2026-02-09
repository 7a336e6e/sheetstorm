---
name: deploying-flask
description: Prepare and deploy the Flask application to a production environment using Gunicorn, Docker, and Nginx.
---

# Deploying Flask

## Goal
Deploy a hardened, production-ready Flask application served by a WSGI server (Gunicorn) behind a reverse proxy (Nginx), preferably containerized with Docker.

## When to Use
- When the application is ready for staging or production release.
- When setting up the CI/CD pipeline for deployment.
- When moving off the development server (`flask run`).

## Instructions

### 1. Production Configuration
Ensure the application loads configuration from environment variables, not hardcoded files.

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    DEBUG = False
    TESTING = False
```

### 2. WSGI Server (Gunicorn)
Never use the built-in Flask development server in production. Use Gunicorn.

Create a `gunicorn_config.py`:
```python
workers = 4 # 2 * CPU cores + 1
bind = "0.0.0.0:8000"
accesslog = "-"
errorlog = "-"
timeout = 120
keepalive = 5
```

### 3. Dockerization
Create a `Dockerfile` optimized for size and security.

```dockerfile
FROM python:3.11-slim-buster

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root user
RUN useradd -m myuser
USER myuser

CMD ["gunicorn", "--config", "gunicorn_config.py", "app:create_app()"]
```

### 4. Reverse Proxy (Nginx)
Use Nginx to handle SSL termination, static files, and request buffering.

```nginx
# nginx.conf snippet
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://flask_app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Constraints

### ✅ Do
- Always use a WSGI server like Gunicorn or uWSGI.
- Run the application as a non-root user inside the container.
- Pin dependencies in `requirements.txt` with exact versions.
- Set `FLASK_ENV` (or `FLASK_DEBUG`) to `production` (or `0`).
- Use environment variables for all secrets (API keys, DB passwords).
- Health check endpoints (`/health`) should verify DB connectivity.


### ❌ Don&#x27;t
- DO NOT use `flask run` in production. It is single-threaded and not secure.
- DO NOT commit `.env` files to the repository.
- DO NOT expose the Gunicorn port directly to the public internet; always use a reverse proxy.
- DO NOT use the default `latest` tag for base images; pin to a specific version (e.g., `python:3.11-slim`).


## Output Format
- `Dockerfile`
- `gunicorn_config.py`
- `docker-compose.yml` (optional, for orchestration)
- Updated `requirements.txt` with `gunicorn`

## Dependencies
- `../scaffolding-flask/SKILL.md`
- `../../shared/environment-config/SKILL.md`
