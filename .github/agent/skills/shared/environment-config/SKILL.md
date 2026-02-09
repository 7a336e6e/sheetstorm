---
name: environment-config
description: The environment-config skill standardizes how agents manage environment variables, secrets, and application configuration across local development and deployed environments.
---

# Environment Configuration

## Goal
Keep application configuration secure, consistent, and well-documented so that any agent or developer can set up and run the project without guessing at required values.

## When to Use
- When adding a new environment variable or secret
- When setting up a new service or integration that requires credentials
- When onboarding a new agent or developer to the project
- When deploying to a new environment (staging, production)

## Instructions

### Step 1: Define Variables in .env.example
Every environment variable used by the project must appear in `.env.example` with a placeholder value and a comment:

```bash
# .env.example — checked into git, safe to share
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/myapp_dev
DATABASE_POOL_SIZE=5

# Authentication
JWT_SECRET=replace-with-a-strong-random-string
JWT_EXPIRY_SECONDS=3600

# External APIs
STRIPE_API_KEY=sk_test_placeholder
SENDGRID_API_KEY=SG.placeholder
```

Copy this file to `.env` for local development and fill in real values. The `.env` file must be in `.gitignore`.

### Step 2: Load Config at Application Startup

**Python (Flask / FastAPI):**
```python
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env into os.environ

class Config:
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    JWT_SECRET: str = os.environ["JWT_SECRET"]
    JWT_EXPIRY: int = int(os.environ.get("JWT_EXPIRY_SECONDS", "3600"))
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

config = Config()
```

**Node.js (Express / Vite):**
```javascript
// config.js
import "dotenv/config";

export const config = {
  databaseUrl: requireEnv("DATABASE_URL"),
  jwtSecret: requireEnv("JWT_SECRET"),
  jwtExpiry: parseInt(process.env.JWT_EXPIRY_SECONDS || "3600", 10),
  debug: process.env.DEBUG === "true",
};

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}
```

### Step 3: Validate Config at Startup
Fail fast if required variables are missing. Do not let the application start with invalid configuration — a clear error at boot is better than a cryptic failure at runtime.

```python
# Python validation example
REQUIRED_VARS = ["DATABASE_URL", "JWT_SECRET", "STRIPE_API_KEY"]

missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
```

```javascript
// Node.js validation example
const REQUIRED = ["DATABASE_URL", "JWT_SECRET", "STRIPE_API_KEY"];
const missing = REQUIRED.filter((key) => !process.env[key]);
if (missing.length > 0) {
  throw new Error(`Missing required env vars: ${missing.join(", ")}`);
}
```

### Step 4: Handle Secrets Safely
- Pass secrets through environment variables, never hardcode them in source
- Never log secret values — mask them in log output if you must reference them
- Rotate secrets on a schedule and immediately if a leak is suspected
- Use distinct secrets per environment (dev, staging, production)

### Step 5: Document Every Variable
Add a comment in `.env.example` explaining each variable's purpose, expected format, and where to obtain its value (e.g., "Get from Stripe dashboard > API keys").

## Constraints

### ✅ Do
- Validate all required config at application startup
- Use `.env.example` as the single source of truth for required variables
- Document every variable with a comment explaining its purpose
- Use different values for each environment (dev, staging, production)
- Add `.env` and `.env.local` to `.gitignore` before the first commit


### ❌ Don&#x27;t
- Never commit `.env` files containing real credentials
- Never hardcode secrets in source code, config files, or tests
- Never log secret values — even at debug level
- Never use default values for secrets in production (fail instead)
- Never share production secrets in chat, tickets, or documentation


## Output Format
Configuration files (`.env.example`, config modules) written to the project root and documented in the project README when applicable.

## Dependencies
- `../git-workflow/SKILL.md` — ensures `.env` is excluded via `.gitignore`
