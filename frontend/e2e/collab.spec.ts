// Live collaboration (W2-RT-FE): two browser contexts on one incident.
// - A adds a host → B sees it without reloading.
// - Presence shows both users; the live dot reports "Live".
// - B saves over a change A made meanwhile → ConflictDialog → overwrite.
// - Removing an assignment sends the assigned-only user back to the list.
// Integrator only: runs against a live stack (see e2e/README.md).
import type { Browser, BrowserContext, Page } from '@playwright/test'
import fs from 'node:fs'
import { storageStatePath, type RoleKey } from './auth'
import { api, expect, expectOk, test } from './fixtures'

const LIVE_TIMEOUT = 5_000

async function contextFor(browser: Browser, role: RoleKey): Promise<BrowserContext | null> {
  const state = storageStatePath(role, 'a')
  if (!fs.existsSync(state)) return null
  return browser.newContext({ storageState: state, baseURL: test.info().project.use.baseURL })
}

async function createIncident(context: BrowserContext, title: string): Promise<string> {
  const res = await expectOk(
    await api.post(context, '/incidents', { title, severity: 'medium', tlp: 'green' }),
    'create incident'
  )
  return ((await res.json()) as { id: string }).id
}

async function me(context: BrowserContext): Promise<{ id: string; name: string }> {
  const res = await expectOk(await api.get(context, '/auth/me'), 'GET /auth/me')
  const body = (await res.json()) as { user?: { id: string; name: string }; id?: string; name?: string }
  return body.user ?? { id: body.id ?? '', name: body.name ?? '' }
}

async function openHosts(page: Page, incidentId: string) {
  await page.goto(`/dashboard/incidents/${incidentId}?tab=hosts`)
  await expect(page.getByRole('grid', { name: 'Compromised hosts' })).toBeVisible()
  await expect(page.getByRole('status', { name: 'Live updates: Live' })).toBeVisible({ timeout: LIVE_TIMEOUT })
}

test.describe('live collaboration @collab', () => {
  test.describe.configure({ mode: 'serial' })

  let a: BrowserContext | null = null // Incident Responder
  let b: BrowserContext | null = null // Administrator
  let incidentId = ''

  test.beforeAll(async ({ browser }) => {
    a = await contextFor(browser, 'responder')
    b = await contextFor(browser, 'admin')
    if (a && b) incidentId = await createIncident(a, `E2E collab ${Date.now()}`)
  })

  test.afterAll(async () => {
    await a?.close()
    await b?.close()
  })

  test.beforeEach(() => {
    test.skip(!a || !b, 'no storage state: set ADMIN_EMAIL/ADMIN_PASSWORD (see e2e/README.md)')
  })

  test('a host added by A appears for B without a list refetch; presence shows both', async () => {
    const pageA = await a!.newPage()
    const pageB = await b!.newPage()
    await openHosts(pageA, incidentId)
    await openHosts(pageB, incidentId)

    await expect(pageA.getByTestId('presence-avatar')).toHaveCount(2, { timeout: LIVE_TIMEOUT })
    await expect(pageB.getByTestId('presence-avatar')).toHaveCount(2, { timeout: LIVE_TIMEOUT })

    let listGets = 0
    pageB.on('request', (req) => {
      if (req.method() === 'GET' && new URL(req.url()).pathname.endsWith(`/incidents/${incidentId}/hosts`)) listGets++
    })
    await expectOk(
      await api.post(a!, `/incidents/${incidentId}/hosts`, { hostname: 'E2E-LIVE-01', ip_address: '10.9.0.1', system_type: 'workstation' }),
      'create host'
    )
    const grid = pageB.getByRole('grid', { name: 'Compromised hosts' })
    await expect(grid.getByText('E2E-LIVE-01')).toBeVisible({ timeout: 2_000 })
    expect(listGets).toBe(0)

    await pageA.close()
    await pageB.close()
  })

  test('saving over a newer version opens the conflict dialog; overwrite wins', async () => {
    const created = await expectOk(
      await api.post(a!, `/incidents/${incidentId}/hosts`, { hostname: 'E2E-CONFLICT-01', ip_address: '10.9.0.2', system_type: 'server' }),
      'create host'
    )
    const hostId = ((await created.json()) as { id: string }).id

    const pageB = await b!.newPage()
    await openHosts(pageB, incidentId)
    await pageB.getByRole('button', { name: /actions for .*E2E-CONFLICT-01/i }).click()
    await pageB.getByRole('menuitem', { name: 'Edit' }).click()
    const form = pageB.getByRole('dialog', { name: /edit compromised host/i })
    await expect(form).toBeVisible()

    // A changes the host while B's form is open.
    await expectOk(
      await api.put(a!, `/incidents/${incidentId}/hosts/${hostId}`, { hostname: 'E2E-CONFLICT-A' }),
      'update host as A'
    )

    await form.getByPlaceholder('e.g. WS-FINANCE-01').fill('E2E-CONFLICT-B')
    await form.getByRole('button', { name: 'Save Changes' }).click()

    const conflict = pageB.getByRole('dialog', { name: 'Changed by someone else' })
    await expect(conflict).toBeVisible()
    await expect(conflict.getByRole('table', { name: 'Conflicting fields' })).toContainText('E2E-CONFLICT-A')
    await conflict.getByRole('button', { name: 'Overwrite with mine' }).click()
    await expect(conflict).toBeHidden()

    const res = await expectOk(await api.get(a!, `/incidents/${incidentId}/hosts?per_page=200`), 'list hosts')
    const hosts = ((await res.json()) as { items: Array<{ id: string; hostname: string }> }).items
    expect(hosts.find((h) => h.id === hostId)?.hostname).toBe('E2E-CONFLICT-B')
    await pageB.close()
  })

  test('removing the assignment of an assigned-only user sends them back to the list', async ({ browser }) => {
    const op = await contextFor(browser, 'operator')
    test.skip(!op, 'no operator storage state')
    try {
      const operator = await me(op!)
      const assigned = await expectOk(
        await api.post(a!, `/incidents/${incidentId}/assignments`, { user_id: operator.id, role: 'investigator' }),
        'assign operator'
      )
      const assignmentId = ((await assigned.json()) as { id: string }).id

      const page = await op!.newPage()
      await page.goto(`/dashboard/incidents/${incidentId}`)
      await expect(page.getByRole('status', { name: 'Live updates: Live' })).toBeVisible({ timeout: LIVE_TIMEOUT })

      await expectOk(await api.delete(a!, `/incidents/${incidentId}/assignments/${assignmentId}`), 'remove assignment')
      await expect(page).toHaveURL(/\/dashboard\/incidents\/?$/, { timeout: LIVE_TIMEOUT })
      // first(): Radix Toast also renders a hidden screen-reader copy for a moment.
      await expect(page.getByText('Access to this incident ended').first()).toBeVisible()
    } finally {
      await op?.close()
    }
  })
})
