// OpenID Connect single sign-on, end to end against the test identity provider
// (ci/mock-oidc, part of the CI e2e stack: ci/compose.e2e.yml).
// - a mapped group signs in, lands on the dashboard and gets its role;
// - a user outside the allowed groups is refused with a readable message;
// - a linked account with SheetStorm TOTP enters a code after the IdP.
// Skips when the mock IdP is not reachable (E2E_OIDC_PUBLIC_URL).
import crypto from 'node:crypto'
import fs from 'node:fs'
import type { Browser, BrowserContext } from '@playwright/test'
import { seedPassword, storageStatePath } from './auth'
import { api, apiLogin, expect, expectOk, test } from './fixtures'

/** Issuer as the backend reaches it, and the IdP's URL as the browser reaches it. */
const ISSUER = process.env.E2E_OIDC_ISSUER || 'http://mock-oidc:9000'
const IDP_PUBLIC = process.env.E2E_OIDC_PUBLIC_URL || 'http://localhost:9000'
const BUTTON = 'E2E Mock IdP'

type Role = { id: string; name: string }
type UserRow = { id: string; email: string; roles?: Array<string | { name: string }> }

async function idpReachable(): Promise<boolean> {
  try {
    return (await fetch(`${IDP_PUBLIC}/healthz`)).ok
  } catch {
    return false
  }
}

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s) from a base32 secret. */
function totp(secret: string, now = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const c of secret.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 30_000)))
  const mac = crypto.createHmac('sha1', key).update(counter).digest()
  const offset = mac[mac.length - 1] & 0xf
  return String((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0')
}

async function findUser(admin: BrowserContext, email: string): Promise<UserRow | undefined> {
  const res = await expectOk(await api.get(admin, `/users?q=${encodeURIComponent(email)}`), 'find user')
  const body = (await res.json()) as { items?: UserRow[]; users?: UserRow[] }
  return (body.items ?? body.users ?? []).find((u) => u.email === email)
}

const roleNames = (u: UserRow | undefined) => (u?.roles ?? []).map((r) => (typeof r === 'string' ? r : r.name))

/** Sign in through the provider's button as one of the mock IdP's users, in a fresh browser. */
async function ssoSignIn(browser: Browser, userName: string) {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL })
  const page = await context.newPage()
  await page.goto('/login')
  await page.getByRole('link', { name: BUTTON }).click()
  await expect(page).toHaveURL(new RegExp(`^${IDP_PUBLIC}/authorize`))
  await page.getByRole('button', { name: `Sign in as ${userName}` }).click()
  return { context, page }
}

test.describe('single sign-on @sso', () => {
  test.describe.configure({ mode: 'serial' })

  const emails = ['alice@mock-idp.example', 'bob@mock-idp.example', 'erin@mock-idp.example']
  let admin: BrowserContext | null = null
  let providerId = ''

  test.beforeAll(async ({ browser }) => {
    const state = storageStatePath('admin', 'a')
    if (!fs.existsSync(state) || !(await idpReachable())) return
    admin = await browser.newContext({ storageState: state, baseURL: test.info().project.use.baseURL })
    // Leftovers of an earlier run would hit "account exists" on a new provider.
    for (const email of emails) {
      const user = await findUser(admin, email)
      if (user) await api.delete(admin, `/users/${user.id}`)
    }
    const roles = ((await (await expectOk(await api.get(admin, '/roles'), 'roles')).json()) as { items: Role[] }).items
    const roleId = (name: string) => roles.find((r) => r.name === name)!.id
    const res = await expectOk(
      await api.post(admin, '/admin/sso-providers', {
        slug: `e2e-mock-${Date.now().toString(36)}`,
        display_name: BUTTON,
        preset: 'generic',
        issuer: ISSUER,
        client_id: 'sheetstorm-e2e',
        client_secret: 'mock-secret',
        scopes: 'openid email profile groups',
        groups_claim: 'groups',
        allowed_groups: ['ir-leads', 'ir-analysts'],
        role_mappings: [
          { group: 'ir-leads', role_id: roleId('Manager') },
          { group: 'ir-analysts', role_id: roleId('Analyst') },
        ],
        auto_provision: true,
        link_existing: true,
      }),
      'create SSO provider'
    )
    providerId = ((await res.json()) as { id: string }).id
  })

  test.afterAll(async () => {
    if (!admin) return
    if (providerId) await api.delete(admin, `/admin/sso-providers/${providerId}`)
    for (const email of emails) {
      const user = await findUser(admin, email)
      if (user) await api.delete(admin, `/users/${user.id}`)
    }
    await admin.close()
  })

  test.beforeEach(() => {
    test.skip(!admin || !providerId, 'needs the admin storage state and the mock IdP (ci/mock-oidc)')
  })

  test('the configuration check passes against the IdP', async () => {
    const report = (await (await expectOk(await api.post(admin!, `/admin/sso-providers/${providerId}/test`), 'test'))
      .json()) as { ok: boolean; checks: Array<{ name: string; ok: boolean }> }
    expect(report.checks.filter((c) => !c.ok)).toEqual([])
    expect(report.ok).toBe(true)
  })

  test('a mapped group signs in, lands on the dashboard and gets its role', async ({ browser }) => {
    const { context, page } = await ssoSignIn(browser, 'Alice Lead')
    try {
      await expect(page).toHaveURL(/\/dashboard\/?$/)
      await expect(page.getByText('Alice Lead').first()).toBeVisible()
      expect(roleNames(await findUser(admin!, 'alice@mock-idp.example'))).toEqual(['Manager'])

      // Signing in again finds the same account (by subject).
      await page.getByRole('button', { name: 'Sign out' }).click()
      await expect(page).toHaveURL(/\/login/)
      await page.getByRole('link', { name: BUTTON }).click()
      await page.getByRole('button', { name: 'Sign in as Alice Lead' }).click()
      await expect(page).toHaveURL(/\/dashboard\/?$/)
    } finally {
      await context.close()
    }
  })

  test('a user outside the allowed groups is refused', async ({ browser }) => {
    const { context, page } = await ssoSignIn(browser, 'Carol Outsider')
    try {
      await expect(page).toHaveURL(/\/login\?sso_error=group_not_allowed/)
      await expect(page.getByTestId('sso-error')).toHaveText('You are not in a group that may sign in to SheetStorm.')
      expect(await findUser(admin!, 'carol@mock-idp.example')).toBeUndefined()
    } finally {
      await context.close()
    }
  })

  test('a linked account with SheetStorm TOTP enters a code after the IdP', async ({ browser }) => {
    // A local account with the same email, enrolled in TOTP.
    const email = 'erin@mock-idp.example'
    const password = seedPassword(email)
    test.skip(!password, 'needs ADMIN_PASSWORD or E2E_SEED_PASSWORD to derive a password')
    await expectOk(await api.post(admin!, '/users', { email, name: 'Erin Local', password, roles: ['Analyst'] }), 'create erin')
    const erin = await browser.newContext({ baseURL: test.info().project.use.baseURL })
    try {
      await apiLogin(erin, email, password!)
      const setup = (await (await expectOk(await api.post(erin, '/auth/mfa/setup'), 'mfa setup')).json()) as { secret: string }
      await expectOk(await api.post(erin, '/auth/mfa/verify', { code: totp(setup.secret) }), 'mfa verify')

      const { context, page } = await ssoSignIn(browser, 'Erin Totp')
      try {
        await expect(page).toHaveURL(/\/login\?sso=mfa/)
        await page.getByLabel(/Authenticator Code/).fill(totp(setup.secret))
        await page.getByRole('button', { name: 'Verify and continue' }).click()
        await expect(page).toHaveURL(/\/dashboard\/?$/)
        await expect(page.getByText('Erin Local').first()).toBeVisible()
      } finally {
        await context.close()
      }
    } finally {
      await erin.close()
    }
  })
})
