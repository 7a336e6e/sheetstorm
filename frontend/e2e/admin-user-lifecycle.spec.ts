// User lifecycle admin UI (W2-LIFE-UI): invites, disable + live session
// revocation, temporary-password forced change, lockout/unlock, bulk actions
// and the "deactivate instead" delete flow.
// Run: npx playwright test e2e/admin-user-lifecycle.spec.ts   (against a running stack)
//
// Passwords for throwaway users are random per run and never stored.
import crypto from 'node:crypto'
import type { Browser, BrowserContext, Page } from '@playwright/test'
import { api, apiLogin, expect, expectOk, test, useRole } from './fixtures'

const stamp = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`
const newEmail = (tag: string) => `e2e.lifecycle.${tag}.${stamp()}@org-a.e2e.sheetstorm.test`

/** Random policy-compliant password (12+, upper, lower, digit, special). */
function randomPassword(): string {
  return `${crypto.randomBytes(12).toString('base64url')}Aa1!`
}

type RoleRow = { id: string; name: string }

async function roleId(context: BrowserContext, name: string): Promise<string> {
  const res = await expectOk(await api.get(context, '/roles'), 'list roles')
  const body = (await res.json()) as { items: RoleRow[] }
  const role = body.items.find((r) => r.name === name)
  if (!role) throw new Error(`role ${name} not found`)
  return role.id
}

/** Create a user through the API and return a logged-in context for it. */
async function createUser(
  browser: Browser,
  admin: BrowserContext,
  tag: string,
  roles: string[] = ['Viewer']
): Promise<{ id: string; email: string; password: string; context: BrowserContext }> {
  const email = newEmail(tag)
  const password = randomPassword()
  const res = await expectOk(
    await api.post(admin, '/users', { email, name: `E2E ${tag}`, password, roles }),
    `create user ${tag}`
  )
  const { id } = (await res.json()) as { id: string }
  const context = await browser.newContext()
  await apiLogin(context, email, password)
  return { id, email, password, context }
}

/** The users page narrowed to one email; returns its row. */
async function userRow(page: Page, email: string) {
  await page.goto(`/dashboard/admin/users?users.q=${encodeURIComponent(email)}`)
  const row = page.getByRole('row').filter({ hasText: email })
  await expect(row).toBeVisible()
  return row
}

async function rowAction(page: Page, email: string, action: string) {
  const row = await userRow(page, email)
  await row.getByRole('button', { name: /actions for/i }).click()
  await page.getByRole('menuitem', { name: action, exact: true }).click()
}

/** Best-effort cleanup: delete, or disable when the user authored records. */
async function removeUser(admin: BrowserContext, id: string) {
  const res = await api.delete(admin, `/users/${id}`)
  if (res.status() === 409) await api.post(admin, `/users/${id}/disable`, { reason: 'e2e cleanup' })
}

async function userIdByEmail(admin: BrowserContext, email: string): Promise<string | undefined> {
  const res = await expectOk(await api.get(admin, `/users?q=${encodeURIComponent(email)}`), 'find user')
  const body = (await res.json()) as { items: { id: string; email: string }[] }
  return body.items.find((u) => u.email === email)?.id
}

test.describe('user lifecycle admin', { tag: '@admin-user-lifecycle' }, () => {
  useRole('admin')

  test('invite link (shown once) lets the invitee join as Analyst', async ({ browser, context, page }) => {
    const email = newEmail('invitee')
    let invitee: BrowserContext | undefined
    try {
      await page.goto('/dashboard/admin/users')
      await page.getByRole('button', { name: 'Invite user' }).click()
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel('Email Address').fill(email)
      await dialog.getByRole('checkbox', { name: 'Analyst', exact: true }).check()
      await dialog.getByRole('button', { name: 'Create invite' }).click()
      await expect(dialog.getByText(`Anyone with this link can join as ${email}`)).toBeVisible()
      const linkField = dialog.getByRole('textbox', { name: 'Invite link', exact: true })
      await expect(linkField).toBeVisible()
      const link = await linkField.inputValue()
      expect(link).toMatch(/\/auth\/invite#token=/)
      await dialog.getByRole('button', { name: 'Done' }).click()

      // Pending invites tab lists it.
      await page.getByRole('tab', { name: 'Pending invites' }).click()
      await expect(page.getByRole('row').filter({ hasText: email })).toBeVisible()

      // The invitee accepts in a fresh context; the token leaves the address bar.
      invitee = await browser.newContext()
      const p = await invitee.newPage()
      await p.goto(link)
      await expect(p.getByText(email).first()).toBeVisible()
      expect(new URL(p.url()).hash).toBe('')
      const password = randomPassword()
      await p.getByLabel('Full name').fill('E2E Invitee')
      await p.getByLabel('Password', { exact: true }).fill(password)
      await p.getByLabel('Confirm password').fill(password)
      await p.getByRole('button', { name: /create account/i }).click()
      await expect(p).toHaveURL(/\/dashboard/)

      // The admin sees the new Analyst.
      const row = await userRow(page, email)
      await expect(row.getByText('Analyst')).toBeVisible()
    } finally {
      const id = await userIdByEmail(context, email)
      if (id) await removeUser(context, id)
      await invitee?.close()
    }
  })

  test('disabling a signed-in user sends their tab to /login (session:revoked)', async ({ browser, context, page }) => {
    const user = await createUser(browser, context, 'disable')
    try {
      const userPage = await user.context.newPage()
      await userPage.goto('/dashboard')
      await expect(userPage).toHaveURL(/\/dashboard/)

      await rowAction(page, user.email, 'Disable')
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel('Reason').fill('E2E suspected compromise')
      await dialog.getByRole('button', { name: 'Disable user' }).click()
      await expect(dialog).toHaveCount(0)
      await expect((await userRow(page, user.email)).getByText('Disabled')).toBeVisible()

      await expect(userPage).toHaveURL(/\/login\?reason=session_revoked/, { timeout: 10_000 })
      await expect(userPage.getByText('Your account was disabled.')).toBeVisible()
    } finally {
      await removeUser(context, user.id)
      await user.context.close()
    }
  })

  test('temporary password forces a change at next sign-in', async ({ browser, context, page }) => {
    const user = await createUser(browser, context, 'temp')
    let fresh: BrowserContext | undefined
    try {
      await rowAction(page, user.email, 'Reset password')
      const dialog = page.getByRole('dialog')
      await dialog.getByLabel(/temporary password/i).check()
      await dialog.getByRole('button', { name: 'Reset password' }).click()
      const tempField = dialog.getByRole('textbox', { name: 'Temporary password', exact: true })
      await expect(tempField).toBeVisible()
      const temp = await tempField.inputValue()
      expect(temp.length).toBeGreaterThanOrEqual(12)
      await dialog.getByRole('button', { name: 'Done' }).click()
      await expect(dialog).toHaveCount(0)

      fresh = await browser.newContext()
      await apiLogin(fresh, user.email, temp)
      const p = await fresh.newPage()
      await p.goto('/dashboard')
      await expect(p).toHaveURL(/\/auth\/change-password/)
      const next = randomPassword()
      await p.getByLabel('Temporary password').fill(temp)
      await p.getByLabel('New password').fill(next)
      await p.getByLabel('Confirm password').fill(next)
      await p.getByRole('button', { name: 'Change password' }).click()
      await expect(p).toHaveURL(/\/dashboard\/?$/)
    } finally {
      await removeUser(context, user.id)
      await user.context.close()
      await fresh?.close()
    }
  })

  test('bulk force logout reports per-user results', async ({ browser, context, page }) => {
    const users = [
      await createUser(browser, context, 'bulk1'),
      await createUser(browser, context, 'bulk2'),
      await createUser(browser, context, 'bulk3'),
    ]
    try {
      await page.goto(`/dashboard/admin/users?users.q=${encodeURIComponent('e2e.lifecycle.bulk')}`)
      for (const u of users) {
        await page.getByRole('row').filter({ hasText: u.email }).getByRole('checkbox', { name: 'Select row' }).check()
      }
      await page.getByRole('button', { name: /bulk actions/i }).click()
      await page.getByRole('menuitem', { name: 'Force logout' }).click()
      await page.getByRole('dialog').getByRole('button', { name: 'Force logout' }).click()
      const result = page.getByRole('dialog', { name: /results/i })
      await expect(result.getByTestId('bulk-summary')).toHaveText('3 succeeded, 0 skipped, 0 failed')
      await result.getByRole('button', { name: 'Close', exact: true }).first().click()

      // Their sessions are dead.
      const res = await api.get(users[0].context, '/auth/me')
      expect(res.status()).toBe(401)
    } finally {
      for (const u of users) {
        await removeUser(context, u.id)
        await u.context.close()
      }
    }
  })

  test('deleting a user who authored an incident offers "Disable instead"', async ({ browser, context, page }) => {
    const user = await createUser(browser, context, 'author', ['Incident Responder'])
    try {
      await expectOk(
        await api.post(user.context, '/incidents', { title: `E2E lifecycle ${stamp()}`, severity: 'low', tlp: 'green' }),
        'create incident as the user'
      )
      await rowAction(page, user.email, 'Delete')
      const confirm = page.getByRole('dialog')
      await confirm.getByRole('textbox').fill(user.email)
      await confirm.getByRole('button', { name: 'Delete' }).click()

      const records = page.getByRole('dialog', { name: /authored records/i })
      await expect(records).toContainText(/incidents/)
      await records.getByRole('button', { name: 'Disable instead' }).click()
      const disable = page.getByRole('dialog', { name: /disable/i })
      await disable.getByLabel('Reason').fill('E2E offboarding')
      await disable.getByRole('button', { name: 'Disable user' }).click()
      await expect((await userRow(page, user.email)).getByText('Disabled')).toBeVisible()
    } finally {
      await removeUser(context, user.id)
      await user.context.close()
    }
  })

  // Needs the stack's LOGIN_LOCKOUT_THRESHOLD exported here as E2E_LOCKOUT_THRESHOLD
  // (≤ 4, so the attempts fit in the 5/min login rate limit).
  test('lockout keeps the right password out until an admin unlocks', async ({ browser, context, page }) => {
    const threshold = Number(process.env.E2E_LOCKOUT_THRESHOLD || 0)
    test.skip(!threshold || threshold > 4, 'set E2E_LOCKOUT_THRESHOLD (3..4) to the stack LOGIN_LOCKOUT_THRESHOLD')
    const user = await createUser(browser, context, 'lockout')
    const probe = await browser.newContext()
    try {
      // Wait out the login limiter used by createUser.
      await new Promise((r) => setTimeout(r, 61_000))
      for (let i = 0; i < threshold; i++) {
        const res = await probe.request.post('/api/v1/auth/login', { data: { email: user.email, password: 'Wrong-pass-123!' } })
        expect(res.status()).toBe(401)
      }
      const locked = await probe.request.post('/api/v1/auth/login', {
        data: { email: user.email, password: user.password },
      })
      expect(locked.status()).toBe(401)

      const row = await userRow(page, user.email)
      await expect(row.getByText('Locked')).toBeVisible()
      await rowAction(page, user.email, 'Unlock')
      await expect((await userRow(page, user.email)).getByText('Locked')).toHaveCount(0)

      await new Promise((r) => setTimeout(r, 61_000))
      await apiLogin(probe, user.email, user.password)
    } finally {
      await removeUser(context, user.id)
      await user.context.close()
      await probe.close()
    }
  })
})
