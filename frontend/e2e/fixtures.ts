// Helpers for specs. Import `test`/`expect` from here (or from
// @playwright/test) and call `useRole()` at the top of a describe block.
import fs from 'node:fs'
import { test, expect, type APIResponse, type BrowserContext } from '@playwright/test'
import { storageStatePath, type OrgKey, type RoleKey } from './auth'

export { test, expect }

/**
 * Run the enclosing describe block as a seeded role user. Skips the block when
 * the storage state is missing (no ADMIN_EMAIL/ADMIN_PASSWORD, or org B not
 * bootstrapped), so the suite stays green without credentials.
 */
export function useRole(role: RoleKey, org: OrgKey = 'a'): void {
  const file = storageStatePath(role, org)
  const present = fs.existsSync(file)
  test.skip(!present, `no storage state ${file}: set ADMIN_EMAIL/ADMIN_PASSWORD (see e2e/README.md)`)
  test.use({ storageState: present ? file : { cookies: [], origins: [] } })
}

const API = '/api/v1'

async function csrfHeader(context: BrowserContext): Promise<Record<string, string>> {
  const csrf = (await context.cookies()).find((c) => c.name === 'csrf_access_token')?.value
  return csrf ? { 'X-CSRF-TOKEN': csrf } : {}
}

/** Cookie-authenticated API calls that share the browser context's session. */
export const api = {
  get: (context: BrowserContext, endpoint: string) => context.request.get(API + endpoint),
  post: async (context: BrowserContext, endpoint: string, data?: unknown) =>
    context.request.post(API + endpoint, { data, headers: await csrfHeader(context) }),
  put: async (context: BrowserContext, endpoint: string, data?: unknown) =>
    context.request.put(API + endpoint, { data, headers: await csrfHeader(context) }),
  delete: async (context: BrowserContext, endpoint: string) =>
    context.request.delete(API + endpoint, { headers: await csrfHeader(context) }),
}

/** Fail with the response body (never the request) when a call is not 2xx. */
export async function expectOk(res: APIResponse, what: string): Promise<APIResponse> {
  if (!res.ok()) throw new Error(`${what}: HTTP ${res.status()} ${await res.text()}`)
  return res
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Log a context in through the API (sets the session cookies on the context).
 * /auth/login is limited to 5/min per IP, so 429s are waited out.
 */
export async function apiLogin(context: BrowserContext, email: string, password: string): Promise<void> {
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await context.request.post(`${API}/auth/login`, { data: { email, password } })
    if (res.status() === 429) {
      const wait = Number(res.headers()['retry-after']) || 15
      await sleep(Math.min(Math.max(wait, 1), 65) * 1000)
      continue
    }
    if (!res.ok()) {
      const body = (await res.json().catch(() => ({}))) as { error?: string; message?: string }
      throw new Error(`login failed for ${email}: HTTP ${res.status()} ${body.error ?? ''} ${body.message ?? ''}`.trim())
    }
    return
  }
  throw new Error(`login failed for ${email}: still rate limited after retries`)
}
