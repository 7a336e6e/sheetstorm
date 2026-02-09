---
name: Configuring CI/CD
description: Set up automated pipelines for linting, testing, and deployment using GitHub Actions.
---

# Configuring CI/CD

## Goal
Automate the verification and delivery process so that code is always tested, secure, and ready for deployment.

## When to Use
- Starting a new project (set up the pipeline immediately).
- Adding a new quality check (linting, type checking).
- Automating deployment to staging/production.

## Instructions

### 1. Define the Workflow
Create `.github/workflows/ci.yml`.
- **Triggers**: `push` to main, `pull_request` to main.
- **Jobs**: Split into `lint`, `test`, `build`.

### 2. Lint & Type Check (Fastest)
Fail fast.
- Run `eslint`, `prettier`, `black`, `ruff`.
- Run type checkers: `tsc`, `mypy`.

### 3. Test (The Gatekeeper)
Run unit and integration tests.
- Set up services (Postgres, Redis) using `services` in GitHub Actions.
- Run `pytest` or `vitest`.
- Upload coverage reports.

### 4. Build & Deploy (Production)
Only run on `push` to main.
- Build Docker images.
- Push to registry (GHCR/ECR/Docker Hub).
- Trigger deployment (e.g., via webhook or SSH).

### Example Workflow Snippet

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: password
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -r requirements.txt
      - run: pytest
```

## Constraints

### ✅ Do
- **DO**: Cache dependencies (`actions/cache`) to speed up builds.
- **DO**: Separate "Checks" (PRs) from "Deployments" (Main).
- **DO**: Use secrets for all sensitive config (`${{ secrets.DB_URL }}`).
- **DO**: Pin action versions (`actions/checkout@v3`).

### ❌ Don't
- **DON'T**: Hardcode credentials in the workflow file.
- **DON'T**: Skip tests on the main branch deployment.
- **DON'T**: Allow the pipeline to succeed if the linter fails.

## Output Format
- `.github/workflows/*.yml` files.

## Dependencies
- `shared/environment-config/SKILL.md`
- `security/auditing-dependencies/SKILL.md`
