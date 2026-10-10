# E2E (Playwright)

Specs run against an **already-running** stack. Nothing here starts servers.

```bash
cd frontend
npx playwright install chromium        # once; browsers are never installed by npm
export E2E_BASE_URL=http://localhost:8080    # default: the compose proxy
export ADMIN_EMAIL=... ADMIN_PASSWORD=...    # bootstrap admin of org A (from your .env)
npm run test:e2e:smoke                 # = playwright test --grep @smoke
npm run test:e2e                       # full suite
```

- `global-setup.ts` logs in as `ADMIN_EMAIL`, creates one user per system role
  (`e2e.<role>@org-a.e2e.sheetstorm.test`) through `POST /users`, logs each in
  and saves its session to `e2e/.auth/<org>-<role>.json` (mode 0600, git- and
  docker-ignored). States younger than `E2E_AUTH_MAX_AGE_MIN` (30) are reused.
- Seeded passwords are derived from `ADMIN_PASSWORD` (HMAC) or taken from
  `E2E_SEED_PASSWORD`; nothing is stored in the repo.
- Without `ADMIN_EMAIL`/`ADMIN_PASSWORD` the setup is a no-op and every
  logged-in spec skips. `E2E_SKIP_SEED=1` skips seeding but reuses existing states.
- `/auth/login` is limited to 5/min per IP: the first seeding run waits out
  429s (about 2-3 minutes). Later runs reuse the states.

## Single sign-on (`@sso`)

`sso.spec.ts` signs in through `ci/mock-oidc`, a small test identity provider
that the CI e2e stack (`ci/compose.e2e.yml`) starts next to SheetStorm. The
specs skip when it is not reachable. Set `E2E_OIDC_PUBLIC_URL` (default
`http://localhost:9000`) and `E2E_OIDC_ISSUER` (default
`http://mock-oidc:9000`) if you run it elsewhere.

## Second organization (cross-org specs)

There is no API to create organizations. On a **test** stack, bootstrap org B once:

```bash
export E2E_ORG_B_ADMIN_EMAIL=admin-b@e2e.sheetstorm.test E2E_ORG_B_ADMIN_PASSWORD='<12+ chars, Aa1!>'
docker compose exec -T -e E2E_ORG_B_ADMIN_EMAIL -e E2E_ORG_B_ADMIN_PASSWORD \
  backend python - < frontend/e2e/seed-second-org.py
```

Keep both variables exported when running Playwright; org B role users are then
seeded the same way (`e2e/.auth/b-<role>.json`).

## Writing specs

```ts
import { test, expect, useRole, api, expectOk } from './fixtures'

test.describe('evidence tab', { tag: '@evidence' }, () => {
  useRole('viewer')            // or useRole('admin', 'b'); skips if no storage state
  test('viewer sees no mutations', async ({ page, context }) => {
    // api.post(context, '/incidents', {...}) uses the session + CSRF header
  })
})
```

Role keys: `admin`, `responder`, `analyst`, `manager`, `operator`, `viewer`.
Tag the must-pass path `@smoke`; feature specs use their own tag.
