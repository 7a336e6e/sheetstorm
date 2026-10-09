// Smoke suite (@smoke): the minimum that must work on every integration merge.
// Run: npx playwright test --grep @smoke   (against a running stack)
import { seedEmail, seedPassword, hasStorageState } from './auth'
import { api, expect, expectOk, test, useRole } from './fixtures'

test.describe('public', { tag: '@smoke' }, () => {
  test('login page renders', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByLabel('Work Email')).toBeVisible()
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in to dashboard/i })).toBeVisible()
  })

  test('signs in through the login form', async ({ page }) => {
    const email = seedEmail('analyst', 'a')
    const password = seedPassword(email)
    test.skip(!password || !hasStorageState('analyst', 'a'), 'needs seeded users (ADMIN_EMAIL/ADMIN_PASSWORD)')

    await page.goto('/login')
    await page.getByLabel('Work Email').fill(email)
    await page.getByLabel('Password', { exact: true }).fill(password!)

    // /auth/login is rate limited per IP and global-setup may just have used
    // the budget: wait out a 429 and submit again.
    for (let attempt = 0; attempt < 4; attempt++) {
      const [res] = await Promise.all([
        page.waitForResponse((r) => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST'),
        page.getByRole('button', { name: /sign in to dashboard/i }).click(),
      ])
      if (res.status() !== 429) break
      await page.waitForTimeout((Number(res.headers()['retry-after']) || 15) * 1000)
    }

    await expect(page).toHaveURL(/\/dashboard(\/|$)/)
  })
})

test.describe('incident responder', { tag: '@smoke' }, () => {
  useRole('responder')

  test('opens an incident', async ({ page, context }) => {
    const title = `E2E smoke ${Date.now()}`
    const res = await expectOk(
      await api.post(context, '/incidents', { title, severity: 'low', tlp: 'green' }),
      'create incident'
    )
    const incident = (await res.json()) as { id: string }

    await page.goto(`/dashboard/incidents/${incident.id}`)
    await expect(page.getByText(title).first()).toBeVisible()
  })
})

test.describe('administrator', { tag: '@smoke' }, () => {
  useRole('admin')

  test('opens the users admin page', async ({ page }) => {
    await page.goto('/dashboard/admin/users')
    await expect(page.getByRole('heading', { name: 'Users', level: 1 })).toBeVisible()
  })
})
