# Contributing to SheetStorm

Thanks for helping. SheetStorm is a DFIR **investigation tracker**: it
structures and documents an investigation (timeline, hosts, indicators,
evidence, decisions). Alert ingestion, triage queues and detection engines
are out of scope, so please open an issue before building a large feature.

## Getting started

```bash
git clone https://github.com/7a336e6e/sheetstorm.git && cd sheetstorm
./start.sh --dev          # builds and starts everything on http://localhost:8080
```

Local setup without Docker, the useful commands and the migration workflow
are in [assets/docs/development.md](assets/docs/development.md).

## Tests

Run what your change touches; CI runs all of it on every pull request.

| Area | Command |
|---|---|
| Backend | `backend/tests/run_in_docker.sh` (real PostgreSQL and Redis in throwaway containers; `-k name` to filter) |
| MCP server / bridge | `scripts/verify-wp.sh --mcp` |
| Frontend | in `frontend/`: `npx tsc --noEmit`, `npm run lint`, `npm test` |
| End-to-end | a running stack plus `npx playwright test` in `frontend/` (see [frontend/e2e/README.md](frontend/e2e/README.md)) |
| Backup / restore | `ci/backup-roundtrip.sh` against a throwaway stack (see the script header) |

New behavior needs tests: backend features get pytest coverage (fixtures in
`backend/tests/conftest.py`), and UI changes get Jest tests next to the
component.

## Ground rules

- **Security baseline.**
  - Every endpoint checks the caller and the permission (`@require_permission` / `@require_incident_access`).
  - Every query is scoped to the caller's organization.
  - State changes are audit-logged.
  - No secrets in code.
  - Outbound URLs go through `validate_outbound_url`.
- **Migrations.** Exactly one Alembic head before and after your migration.
  `backend/tests/test_migrations.py` checks it.
- **Dependencies.** Follow the [supply-chain policy](assets/docs/supply-chain.md):
  - exact pins;
  - a release must be at least 7 days old (14 for a new package);
  - `npm ci --ignore-scripts`;
  - regenerate the Python locks with `scripts/lock-python.sh`.

  Explain every new dependency in the pull request.
- **Small, focused pull requests.** Don't add unrelated refactors or reformatting.
- **Commit messages.** [Conventional Commits](https://www.conventionalcommits.org/)
  style: `feat(scope): …`, `fix: …`, `docs: …`, `chore: …`.
- **Changelog.** User-visible changes get a line under `## Unreleased` in
  [CHANGELOG.md](CHANGELOG.md). Behavior changes go under "Behavior changes
  (upgrade notes)".

## Pull requests

1. Fork, branch from `main`, and push your branch.
2. Open a pull request using the template; CI must pass.
3. A maintainer reviews it and merges it.

Security problems: please follow [SECURITY.md](SECURITY.md) instead of opening
an issue.

## Releases

Maintainers cut releases by tagging `vX.Y.Z`; see
[Operations → Releases](assets/docs/operations.md#releases-maintainers).
