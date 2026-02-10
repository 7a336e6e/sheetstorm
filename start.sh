#!/bin/bash
set -e

echo "==================================="
echo "SheetStorm - Incident Response Platform"
echo "==================================="

# Ensure persistent data directories exist
mkdir -p data/postgres data/redis

# Check for .env file
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "WARNING: Please update .env with secure values before production use!"
fi

# Generate keys if not set
source .env

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "changeme_generate_32_char_random_string" ]; then
    echo "Generating SECRET_KEY..."
    NEW_SECRET=$(openssl rand -hex 32)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    else
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" .env
    fi
fi

if [ -z "$JWT_SECRET_KEY" ] || [ "$JWT_SECRET_KEY" = "changeme_generate_another_32_char_string" ]; then
    echo "Generating JWT_SECRET_KEY..."
    NEW_JWT_SECRET=$(openssl rand -hex 32)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$NEW_JWT_SECRET/" .env
    else
        sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$NEW_JWT_SECRET/" .env
    fi
fi

if [ -z "$FERNET_KEY" ] || [ "$FERNET_KEY" = "changeme_generate_fernet_key_base64" ]; then
    echo "Generating FERNET_KEY..."
    NEW_FERNET=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|FERNET_KEY=.*|FERNET_KEY=$NEW_FERNET|" .env
    else
        sed -i "s|FERNET_KEY=.*|FERNET_KEY=$NEW_FERNET|" .env
    fi
fi

echo ""
echo "Building containers..."
docker compose build

echo ""
echo "Starting services..."
docker compose up -d

echo ""
echo "Waiting for database to be ready..."
sleep 5

echo ""
echo "Running database migrations..."
docker compose exec -T backend flask db upgrade || echo "Migrations may have already run"

echo ""
echo "Seeding initial data..."
docker compose exec -T backend python -c "from app.seed import seed_all; seed_all()" || echo "Seeding may have already run"

echo ""
echo "==================================="
echo "SheetStorm is running!"
echo "==================================="
echo ""
echo "Frontend: http://127.0.0.1:3000"
echo "Backend API: http://127.0.0.1:5000/api/v1"
echo ""
echo "Default admin credentials:"
echo "  Email: admin@sheetstorm.local"
echo "  Password: (check ADMIN_PASSWORD in .env)"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop: docker compose down"
echo ""
