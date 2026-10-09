// Incident detail tables (W1-TBL): server paging over a large host list,
// `?tab=&row=` deep-link focus, URL-kept list state and Viewer gating.
// Integrator only: runs against a live stack (see e2e/README.md).
import type { BrowserContext } from '@playwright/test'
import fs from 'node:fs'
import { storageStatePath } from './auth'
import { api, expect, expectOk, test, useRole } from './fixtures'

const HOSTS = 120

async function createIncident(context: BrowserContext, title: string): Promise<string> {
  const res = await expectOk(
    await api.post(context, '/incidents', { title, severity: 'medium', tlp: 'green' }),
    'create incident'
  )
  return ((await res.json()) as { id: string }).id
}

async function seedHosts(context: BrowserContext, incidentId: string): Promise<Record<string, string>> {
  const ids: Record<string, string> = {}
  // Sequential on purpose: stays well under the default per-user API limit.
  for (let i = 1; i <= HOSTS; i++) {
    const hostname = `E2E-HOST-${String(i).padStart(3, '0')}`
    const res = await expectOk(
      await api.post(context, `/incidents/${incidentId}/hosts`, {
        hostname,
        ip_address: `10.20.${Math.floor(i / 250)}.${i % 250}`,
        system_type: 'workstation',
        containment_status: i % 2 ? 'active' : 'isolated',
      }),
      `create host ${hostname}`
    )
    ids[hostname] = ((await res.json()) as { id: string }).id
  }
  return ids
}

test.describe('incident tables', () => {
  useRole('responder')
  test.describe.configure({ mode: 'serial' })

  let incidentId = ''
  let hostIds: Record<string, string> = {}

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(180_000)
    const state = storageStatePath('responder', 'a')
    if (!fs.existsSync(state)) return // useRole() skips the tests
    const context = await browser.newContext({ storageState: state, baseURL: test.info().project.use.baseURL })
    try {
      incidentId = await createIncident(context, `E2E tables ${Date.now()}`)
      hostIds = await seedHosts(context, incidentId)
    } finally {
      await context.close()
    }
  })

  test('pages through 120 hosts on the server', async ({ page }) => {
    await page.goto(`/dashboard/incidents/${incidentId}?tab=hosts`)
    const grid = page.getByRole('grid', { name: 'Compromised hosts' })
    await expect(grid).toBeVisible()
    await expect(page.getByText(`1–50 of ${HOSTS}`)).toBeVisible()

    await page.getByRole('button', { name: 'Next page' }).click()
    await expect(page.getByText(`51–100 of ${HOSTS}`)).toBeVisible()
    await expect(page).toHaveURL(/hosts\.page=2/)

    await page.getByRole('button', { name: 'Last page' }).click()
    await expect(page.getByText(`101–120 of ${HOSTS}`)).toBeVisible()
    await expect(grid.getByRole('row')).toHaveCount(1 + 20) // header + rows

    // Sorting by hostname is server-side across every page.
    await page.getByRole('button', { name: /^hostname/i }).click()
    await expect(page).toHaveURL(/hosts\.sort=hostname/)
    await expect(page.getByText(`1–50 of ${HOSTS}`)).toBeVisible()
    await expect(grid.getByRole('row').nth(1)).toContainText('E2E-HOST-001')
  })

  test('keeps search and filters in the URL across reloads', async ({ page }) => {
    await page.goto(`/dashboard/incidents/${incidentId}?tab=hosts`)
    await page.getByRole('searchbox', { name: /search hosts/i }).fill('E2E-HOST-11')
    await expect(page).toHaveURL(/hosts\.q=E2E-HOST-11/)
    // 110..119 match.
    await expect(page.getByText('1–10 of 10')).toBeVisible()

    await page.reload()
    await expect(page.getByRole('searchbox', { name: /search hosts/i })).toHaveValue('E2E-HOST-11')
    await expect(page.getByText('1–10 of 10')).toBeVisible()
  })

  test('?tab=&row= lands on the page containing the row and highlights it', async ({ page }) => {
    // Default sort is -first_seen, then id: find the row wherever it lands.
    const target = 'E2E-HOST-007'
    await page.goto(`/dashboard/incidents/${incidentId}?tab=hosts&row=${hostIds[target]}`)
    const row = page.getByRole('row').filter({ hasText: target })
    await expect(row).toBeVisible()
    await expect(row).toHaveClass(/ring-primary/)
    await expect(page.getByRole('tab', { name: /hosts/i })).toHaveAttribute('data-state', 'active')
  })

  test('?tab=artifacts still opens the evidence tab', async ({ page }) => {
    await page.goto(`/dashboard/incidents/${incidentId}?tab=artifacts`)
    await expect(page.getByRole('tab', { name: /artifacts/i })).toHaveAttribute('data-state', 'active')
  })
})

test.describe('incident tables as Viewer', () => {
  useRole('viewer')

  test('shows no mutation controls on the list tabs', async ({ page, context }) => {
    // A Viewer only sees TLP:WHITE incidents it is not assigned to; it cannot
    // create one, so use an existing visible incident if there is one.
    const res = await api.get(context, '/incidents?per_page=1')
    const items = res.ok() ? ((await res.json()) as { items: { id: string }[] }).items : []
    test.skip(items.length === 0, 'no incident visible to the Viewer')

    for (const tab of ['hosts', 'accounts', 'network', 'host-iocs', 'malware', 'events', 'tasks', 'notes']) {
      await page.goto(`/dashboard/incidents/${items[0].id}?tab=${tab}`)
      await expect(page.getByRole('tabpanel').filter({ visible: true })).toBeVisible()
      await expect(page.getByRole('button', { name: /^(add|new|create)\b/i })).toHaveCount(0)
      await expect(page.getByRole('button', { name: /^actions for/i })).toHaveCount(0)
    }
  })
})
