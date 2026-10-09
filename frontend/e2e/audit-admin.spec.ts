// Audit and admin overview UI (W2-AUD-UI): overview landing, activity filters
// in the URL + diff viewer, export gating, audit retention confirmation,
// legal hold and the integrity check.
// Run: npx playwright test e2e/audit-admin.spec.ts   (against a running stack)
import { api, expect, expectOk, test, useRole } from './fixtures'

const stamp = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`

type AuditSettings = { audit_retention_days: number | null; legal_hold: boolean }

test.describe('audit admin (Administrator)', { tag: '@audit-admin' }, () => {
  useRole('admin')

  test('/dashboard/admin lands on the overview with users, audit and status cards', async ({ page }) => {
    await page.goto('/dashboard/admin')
    await expect(page).toHaveURL(/\/dashboard\/admin\/overview$/)
    await expect(page.getByRole('heading', { name: 'Admin overview' })).toBeVisible()
    await expect(page.getByTestId('overview-users')).toBeVisible()
    await expect(page.getByTestId('overview-audit')).toBeVisible()
    await expect(page.getByTestId('system-status')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
  })

  test('a role edit shows up under "Admin changes only" with its diff', async ({ context, page }) => {
    const name = `E2E Audit Role ${stamp()}`
    const res = await expectOk(await api.post(context, '/roles', { name, permissions: ['incidents:read'] }), 'create role')
    const role = (await res.json()) as { id: string }
    try {
      await expectOk(
        await api.put(context, `/roles/${role.id}`, { permissions: ['incidents:read', 'reports:read'] }),
        'update role'
      )
      await page.goto('/dashboard/activity')
      await page.getByRole('button', { name: 'Filters' }).click()
      await page.getByRole('switch', { name: 'Admin changes only' }).click()
      await expect(page).toHaveURL(/audit\.f\.has_changes=true/)
      await page.getByLabel('Resource ID').fill(role.id)
      await page.getByLabel('Resource ID').press('Enter')
      await expect(page).toHaveURL(new RegExp(`audit\\.f\\.resource_id=${role.id}`))

      const row = page.getByRole('row').filter({ hasText: /Update Role/i }).first()
      await row.getByRole('button', { name: 'Expand row' }).click()
      const changes = page.getByRole('table', { name: 'Changes' })
      await expect(changes.getByRole('list', { name: 'added' })).toContainText('reports:read')

      // The filtered view survives a reload (state is in the URL).
      await page.reload()
      await expect(page.getByRole('row').filter({ hasText: /Update Role/i }).first()).toBeVisible()
    } finally {
      await api.delete(context, `/roles/${role.id}`)
    }
  })

  test('exports the filtered log as CSV', async ({ page }) => {
    await page.goto('/dashboard/activity?audit.f.event_type=admin_action')
    await page.getByRole('button', { name: /^export$/i }).click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('menuitem', { name: 'CSV' }).click(),
    ])
    expect(download.suggestedFilename()).toMatch(/^audit-[a-z0-9-]+-\d{8}T\d{6}Z\.csv$/)
  })

  test.describe('retention and legal hold', () => {
    test.describe.configure({ mode: 'serial' })

    test('shortening retention asks for a typed confirmation with the purge count', async ({ context, page }) => {
      const before = (await (await expectOk(await api.get(context, '/admin/audit-settings'), 'settings')).json()) as AuditSettings
      try {
        await expectOk(await api.put(context, '/admin/audit-settings', { audit_retention_days: null }), 'keep forever')
        await page.goto('/dashboard/admin/settings?tab=audit-retention')
        await page.getByRole('radio', { name: /7 years/ }).check()
        await page.getByRole('button', { name: 'Save retention' }).click()

        const dialog = page.getByRole('dialog')
        await expect(dialog.getByText('Shorten audit retention?')).toBeVisible()
        await expect(dialog.getByTestId('would-purge')).toContainText(/older than the new cutoff/)
        const confirm = dialog.getByRole('button', { name: 'Shorten retention' })
        await expect(confirm).toBeDisabled()
        await dialog.getByRole('textbox').fill('2555')
        await confirm.click()
        await expect(page.getByTestId('current-retention')).toHaveText('2555 days')
      } finally {
        await api.put(context, '/admin/audit-settings', { audit_retention_days: before.audit_retention_days, confirm: true })
      }
    })

    test('a legal hold needs a reason and can be released', async ({ context, page }) => {
      try {
        await page.goto('/dashboard/admin/settings?tab=audit-retention')
        const toggle = page.getByRole('switch', { name: /Legal hold is/ })
        await toggle.click()
        const place = page.getByRole('button', { name: 'Place legal hold' })
        await expect(place).toBeDisabled()
        await page.getByLabel('Reason (required)').fill(`E2E hold ${stamp()}`)
        await place.click()
        await expect(page.getByText('Legal hold is on')).toBeVisible()

        await toggle.click()
        await page.getByRole('dialog').getByRole('button', { name: 'Release hold' }).click()
        await expect(page.getByText('Legal hold is off')).toBeVisible()
      } finally {
        await api.put(context, '/admin/audit-settings', { legal_hold: false })
      }
    })

    test('the integrity check shows the chain result', async ({ page }) => {
      await page.goto('/dashboard/admin/settings?tab=audit-retention')
      await page.getByRole('button', { name: 'Verify now' }).click()
      await expect(page.getByTestId('audit-integrity').getByRole('status')).toContainText(/Chain verifi/)
    })
  })
})

test.describe('audit admin (Manager)', { tag: '@audit-admin' }, () => {
  useRole('manager')

  test('reads the audit log but sees no Export and cannot open the overview', async ({ page }) => {
    await page.goto('/dashboard/activity')
    await expect(page.getByRole('grid', { name: 'Audit log' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^export$/i })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Overview' })).toHaveCount(0)

    await page.goto('/dashboard/admin/overview')
    await expect(page).toHaveURL(/\/dashboard$/)
  })
})
