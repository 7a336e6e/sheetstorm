// Admin guardrails (W1-RBAC-UI): permission-driven admin UI, role cloning,
// grant ceilings, self/last-admin guards and the live permissions_changed refresh.
// Run: npx playwright test e2e/admin-guardrails.spec.ts   (against a running stack)
import type { Browser, BrowserContext, Page } from '@playwright/test'
import { seedPassword } from './auth'
import { api, apiLogin, expect, expectOk, test, useRole } from './fixtures'

type RoleRow = { id: string; name: string; permissions: string[]; is_system: boolean }

const stamp = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`

async function rolesByName(context: BrowserContext): Promise<Map<string, RoleRow>> {
  const res = await expectOk(await api.get(context, '/roles'), 'list roles')
  const body = (await res.json()) as { items: RoleRow[] }
  return new Map(body.items.map((r) => [r.name, r]))
}

/** Create a user through the API (as the admin context) and return a logged-in context for it. */
async function createUser(
  browser: Browser,
  admin: BrowserContext,
  name: string,
  roles: string[]
): Promise<{ id: string; email: string; context: BrowserContext }> {
  const email = `e2e.guardrails.${stamp()}@org-a.e2e.sheetstorm.test`
  const password = seedPassword(email)
  test.skip(!password, 'needs ADMIN_PASSWORD or E2E_SEED_PASSWORD to derive a password')
  const res = await expectOk(
    await api.post(admin, '/users', { email, name, password, roles }),
    `create user ${name}`
  )
  const { id } = (await res.json()) as { id: string }
  const context = await browser.newContext()
  await apiLogin(context, email, password!)
  return { id, email, context }
}

/** The users page (W2-LIFE-UI: server-paged DataTable) narrowed to one email; returns its row. */
async function userRow(page: Page, email: string) {
  await page.goto(`/dashboard/admin/users?users.q=${encodeURIComponent(email)}`)
  const row = page.getByRole('row').filter({ hasText: email })
  await expect(row).toBeVisible()
  return row
}

test.describe('admin guardrails', { tag: '@admin-guardrails' }, () => {
  useRole('admin')

  test('cloned role assigned to a user updates their UI live (permissions_changed)', async ({ browser, context, page }) => {
    const cloneName = `E2E Analyst+audit ${stamp()}`
    const user = await createUser(browser, context, 'E2E Live Perms', ['Viewer'])
    let cloneId: string | undefined
    try {
      // Admin clones Analyst in the UI.
      await page.goto('/dashboard/admin/roles')
      const analystRow = page.getByRole('row').filter({ has: page.getByText('Analyst', { exact: true }) })
      await analystRow.getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Clone' }).click()
      await page.getByLabel('Name').fill(cloneName)
      await page.getByRole('button', { name: 'Clone' }).click()
      await expect(page.getByRole('row').filter({ hasText: cloneName })).toBeVisible()

      // Edit the clone: add "View audit logs".
      cloneId = (await rolesByName(context)).get(cloneName)?.id
      expect(cloneId).toBeTruthy()
      const cloneRow = page.getByRole('row').filter({ hasText: cloneName })
      await cloneRow.getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Edit role' }).click()
      await page.getByRole('checkbox', { name: 'View audit logs' }).check()
      await page.getByRole('button', { name: 'Save changes' }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)

      // The user sees no Admin section yet.
      const userPage = await user.context.newPage()
      await userPage.goto('/dashboard')
      await expect(userPage.getByRole('link', { name: 'Activity' })).toHaveCount(0)

      // Assign the clone; the user's sidebar updates without a reload.
      await expectOk(await api.post(context, `/users/${user.id}/roles`, { role_id: cloneId }), 'assign clone')
      await expect(userPage.getByRole('link', { name: 'Activity' })).toBeVisible({ timeout: 15_000 })
    } finally {
      await api.delete(context, `/users/${user.id}`)
      if (cloneId) await api.delete(context, `/roles/${cloneId}`)
      await user.context.close()
    }
  })

  test('a deputy cannot disable the Administrator nor grant the Administrator role', async ({ browser, context }) => {
    const roleName = `E2E Deputy ${stamp()}`
    const roleRes = await expectOk(
      await api.post(context, '/roles', {
        name: roleName,
        permissions: ['users:read', 'users:update', 'users:manage', 'roles:manage'],
      }),
      'create deputy role'
    )
    const role = (await roleRes.json()) as { id: string }
    const deputy = await createUser(browser, context, 'E2E Deputy', [roleName])
    const target = await createUser(browser, context, 'E2E Target Admin', ['Administrator'])
    try {
      const page = await deputy.context.newPage()
      const row = await userRow(page, target.email)
      await row.getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Edit', exact: true }).click()
      const dialog = page.getByRole('dialog')
      // The modal knows the target outranks the deputy.
      await expect(dialog.getByText("This user holds permissions you don't have")).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Save Changes' })).toBeDisabled()

      // The server refuses anyway (403 insufficient_privilege).
      const res = await api.put(deputy.context, `/users/${target.id}`, { is_active: false })
      expect(res.status()).toBe(403)
      expect(((await res.json()) as { error: string }).error).toBe('insufficient_privilege')

      // On a peer, the Administrator role is offered but disabled.
      const peer = await createUser(browser, context, 'E2E Peer', ['Viewer'])
      try {
        await (await userRow(page, peer.email)).getByRole('button', { name: /actions for/i }).click()
        await page.getByRole('menuitem', { name: 'Edit', exact: true }).click()
        await page.getByRole('combobox', { name: 'Add role' }).click()
        await expect(page.getByRole('option', { name: /Administrator \(exceeds your permissions\)/ })).toHaveAttribute(
          'aria-disabled',
          'true'
        )
      } finally {
        await api.delete(context, `/users/${peer.id}`)
        await peer.context.close()
      }
    } finally {
      await api.delete(context, `/users/${target.id}`)
      await api.delete(context, `/users/${deputy.id}`)
      await api.delete(context, `/roles/${role.id}`)
      await target.context.close()
      await deputy.context.close()
    }
  })

  test('an admin cannot remove their own Administrator role (409)', async ({ browser, context }) => {
    const admin = await createUser(browser, context, 'E2E Self Admin', ['Administrator'])
    try {
      const me = (await (await expectOk(await api.get(admin.context, '/auth/me'), 'me')).json()) as { id: string }
      const adminRole = (await rolesByName(admin.context)).get('Administrator')!
      const res = await api.delete(admin.context, `/users/${me.id}/roles/${adminRole.id}`)
      expect(res.status()).toBe(409)
      expect(['self_lockout', 'last_admin']).toContain(((await res.json()) as { error: string }).error)

      // Same refusal through the UI. A second role keeps the client-side
      // "at least one role" rule from answering first.
      const viewer = (await rolesByName(context)).get('Viewer')!
      await expectOk(await api.post(context, `/users/${admin.id}/roles`, { role_id: viewer.id }), 'add viewer')
      const page = await admin.context.newPage()
      await (await userRow(page, admin.email)).getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Edit', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog.getByRole('switch')).toHaveCount(0) // no self-disable
      await expect(dialog.getByLabel(/Reset Password/)).toHaveCount(0) // no self password reset
      await dialog.getByRole('button', { name: 'Remove role Administrator' }).click()
      await expect(dialog.getByRole('alert')).toContainText(/Would lock you out|Last administrator/)
    } finally {
      await api.delete(context, `/users/${admin.id}`)
      await admin.context.close()
    }
  })

  test('general settings persist (timezone)', async ({ context, page }) => {
    const before = (await (await expectOk(await api.get(context, '/organization'), 'get org')).json()) as {
      settings: { timezone?: string }
    }
    const original = before.settings.timezone || 'UTC'
    const next = original === 'Asia/Tokyo' ? 'Europe/London' : 'Asia/Tokyo'
    try {
      await page.goto('/dashboard/admin/settings?tab=general')
      await page.getByLabel('Timezone').click()
      await page.getByRole('option', { name: next === 'Asia/Tokyo' ? 'Japan (JST)' : 'London (GMT)' }).click()
      await page.getByRole('button', { name: 'Save changes' }).click()
      await expect(page.getByText('Settings saved').first()).toBeVisible()
      await page.reload()
      await expect(page.getByLabel('Timezone')).toContainText(next === 'Asia/Tokyo' ? 'Japan (JST)' : 'London (GMT)')
      // The Data egress card shows red enrichment locked.
      await expect(page.getByTestId('enrichment-red-locked')).toHaveText(/Always blocked/)
    } finally {
      await api.put(context, '/organization', { settings: { timezone: original } })
    }
  })

  test('removed admin pages are gone', async ({ page }) => {
    for (const path of ['/dashboard/admin/sso', '/dashboard/admin/security', '/dashboard/admin/organization']) {
      const res = await page.goto(path)
      expect(res?.status(), path).toBe(404)
    }
  })
})

test.describe('analyst', { tag: '@admin-guardrails' }, () => {
  useRole('analyst')

  test('sees no Admin navigation and is redirected away from settings', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText('Admin', { exact: true })).toHaveCount(0)
    await page.goto('/dashboard/admin/settings')
    await expect(page).toHaveURL(/\/dashboard\/?$/)
  })
})
