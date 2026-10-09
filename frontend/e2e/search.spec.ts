// Global search, command palette, incidents list and notifications (W1-LST).
// Run against a running stack: npx playwright test e2e/search.spec.ts
import { api, expect, expectOk, test, useRole } from './fixtures'

function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

test.describe('command palette and search page', () => {
  useRole('responder')

  test('mod+K finds a host and lands on its row', async ({ page, context }) => {
    const hostname = unique('e2e-ws')
    const inc = (await (
      await expectOk(await api.post(context, '/incidents', { title: unique('E2E search'), severity: 'low', tlp: 'green' }), 'create incident')
    ).json()) as { id: string }
    const host = (await (
      await expectOk(await api.post(context, `/incidents/${inc.id}/hosts`, { hostname, system_type: 'workstation' }), 'create host')
    ).json()) as { id: string }

    await page.goto('/dashboard')
    await page.keyboard.press('ControlOrMeta+k')
    const input = page.getByRole('combobox', { name: 'Search or jump to' })
    await expect(input).toBeFocused()

    await input.fill(hostname)
    const hosts = page.getByRole('group', { name: /^Hosts \(\d+\)$/ })
    await expect(hosts.getByRole('option').first()).toContainText(hostname)

    // Walk to the host hit with the keyboard and open it.
    for (let i = 0; i < 10; i++) {
      const activeId = await input.getAttribute('aria-activedescendant')
      const text = activeId ? await page.locator(`[id="${activeId}"]`).textContent() : ''
      if (text?.includes(hostname)) break
      await input.press('ArrowDown')
    }
    await input.press('Enter')

    await expect(page).toHaveURL(new RegExp(`/dashboard/incidents/${inc.id}\\?tab=hosts&row=${host.id}`))
  })

  test('palette "See all" opens the search page with URL state', async ({ page, context }) => {
    const marker = unique('e2e-note')
    const inc = (await (
      await expectOk(await api.post(context, '/incidents', { title: `${marker} incident`, severity: 'low', tlp: 'green' }), 'create incident')
    ).json()) as { id: string }

    await page.goto('/dashboard/incidents')
    await page.getByRole('button', { name: /^Search/ }).first().click()
    const input = page.getByRole('combobox', { name: 'Search or jump to' })
    await input.fill(marker)
    await page.getByRole('option', { name: /See all \d+ results?/ }).click()

    await expect(page).toHaveURL(new RegExp(`/dashboard/search\\?q=${marker}`))
    const table = page.getByRole('grid', { name: 'Search results' })
    await expect(table.getByText(`${marker} incident`).first()).toBeVisible()

    await table.getByText(`${marker} incident`).first().click()
    await expect(page).toHaveURL(new RegExp(`/dashboard/incidents/${inc.id}`))
  })

  test('`?` opens the shortcuts help and `g i` goes to incidents', async ({ page }) => {
    await page.goto('/dashboard')
    await page.keyboard.press('Shift+?')
    await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible()
    await page.keyboard.press('Escape')
    await page.keyboard.press('g')
    await page.keyboard.press('i')
    await expect(page).toHaveURL(/\/dashboard\/incidents$/)
  })
})

test.describe('incidents list', () => {
  useRole('responder')

  test('filters and search live in the URL and survive reload', async ({ page, context }) => {
    const title = unique('E2E list')
    await expectOk(await api.post(context, '/incidents', { title, severity: 'critical', tlp: 'green' }), 'create incident')

    await page.goto('/dashboard/incidents')
    await page.getByRole('searchbox', { name: /search title/i }).fill(title)
    await expect(page).toHaveURL(/inc\.q=/)
    await expect(page.getByRole('grid', { name: 'Incidents' }).getByText(title)).toBeVisible()

    await page.reload()
    await expect(page.getByRole('searchbox', { name: /search title/i })).toHaveValue(title)
    await expect(page.getByRole('grid', { name: 'Incidents' }).getByText(title)).toBeVisible()
  })
})

test.describe('incidents list as viewer', () => {
  useRole('viewer')

  test('shows no create or archive controls', async ({ page }) => {
    await page.goto('/dashboard/incidents')
    await expect(page.getByRole('heading', { name: 'Incidents', level: 1 })).toBeVisible()
    await expect(page.getByRole('button', { name: /new incident/i })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /actions for/i })).toHaveCount(0)
  })
})
