# Backend tests

The suite runs against real PostgreSQL and Redis. Use the Docker runner, which
creates throwaway containers on a private network (no host ports, nothing
shared with the compose stack) and removes them afterwards:

```bash
backend/tests/run_in_docker.sh            # full suite
backend/tests/run_in_docker.sh -k custody # pytest args pass through
```

Each run rebuilds the test database from `database/init/*.sql` plus the full
Alembic chain, so the fresh-install migration path is exercised every time.
`conftest.py` refuses to wipe a database whose name does not contain `test`.

Runs are parallel-safe (unique, labelled resource names per run; `TEST_RUN_ID`
to choose the id, `IMAGE` to keep a named image tag). See
`assets/docs/development.md` for details.

Fixtures (see `conftest.py`): `app`, `db`, `org_a`/`org_b`, `users` (one user
per system role in org A + `admin_b` in org B), `auth(user, mode='bearer'|'cookie')`,
`make_incident(...)`, `redis_client`, `make_user(org, perms=None, roles=None)`,
`fresh_user(role='Analyst', org=None)`, `platform_org`, `platform_admin`.
Feature fixtures go in `fixtures/<feature>.py` and are loaded automatically.
