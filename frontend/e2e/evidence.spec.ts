// Evidence tab (W3-EVD-UI): register an item, check it out to a new external
// party, acknowledge, check it in, see the chain verified, download the
// printable custody form; plus permission gating (Viewer / Responder / Admin)
// and legal hold blocking disposal.
// Integrator only: runs against a live stack (see e2e/README.md).
import type { BrowserContext } from '@playwright/test'
import fs from 'node:fs'
import { storageStatePath } from './auth'
import { api, expect, expectOk, test, useRole } from './fixtures'

const stamp = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`
const SHA256 = 'ab'.repeat(32)

async function createIncident(context: BrowserContext, title: string, tlp = 'white'): Promise<string> {
  const res = await expectOk(await api.post(context, '/incidents', { title, severity: 'medium', tlp }), 'create incident')
  return ((await res.json()) as { id: string }).id
}

async function registerItem(context: BrowserContext, incidentId: string, title: string): Promise<string> {
  const res = await expectOk(
    await api.post(context, `/incidents/${incidentId}/evidence`, {
      title,
      evidence_type: 'storage_media',
      serial_number: `SN-${stamp()}`,
      acquisition_hashes: [{ algorithm: 'sha256', value: SHA256, source: 'tool_reported' }],
    }),
    'register evidence'
  )
  return ((await res.json()) as { id: string }).id
}

test.describe('evidence: custody workflow', { tag: '@evidence' }, () => {
  useRole('responder')
  test.describe.configure({ mode: 'serial' })

  let incidentId = ''

  test.beforeAll(async ({ browser }) => {
    const state = storageStatePath('responder', 'a')
    if (!fs.existsSync(state)) return // useRole() skips the tests
    const context = await browser.newContext({ storageState: state, baseURL: test.info().project.use.baseURL })
    try {
      incidentId = await createIncident(context, `E2E evidence ${stamp()}`)
    } finally {
      await context.close()
    }
  })

  test('register, check out to a new party, acknowledge, check in, verify chain, download the form', async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000)
    const title = `E2E laptop ${stamp()}`
    await page.goto(`/dashboard/incidents/${incidentId}?tab=evidence`)
    await expect(page.getByRole('grid', { name: 'Evidence register' })).toBeVisible()

    // Register (title + SHA-256); a short hash is refused client-side first.
    await page.getByRole('button', { name: 'Register evidence' }).click()
    const register = page.getByRole('dialog', { name: 'Register evidence' })
    await register.getByLabel('Title').fill(title)
    await register.getByLabel('Hash 1 value').fill('abc123')
    await register.getByRole('button', { name: 'Register' }).click()
    await expect(register.getByText(/SHA-256 must be 64 characters/)).toBeVisible()
    await register.getByLabel('Hash 1 value').fill(SHA256)
    await register.getByRole('button', { name: 'Register' }).click()

    // The new item opens in the drawer.
    const drawer = page.getByRole('dialog').filter({ hasText: title })
    await expect(drawer.getByText(/^EV-\d{4}$/).first()).toBeVisible()
    await expect(drawer.getByText('In storage').first()).toBeVisible()

    // A responder cannot dispose or void (needs artifacts:delete).
    await drawer.getByRole('button', { name: /^Actions for EV-/ }).click()
    await expect(page.getByRole('menuitem', { name: /Check out/ })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /Dispose/ })).toHaveCount(0)
    await expect(page.getByRole('menuitem', { name: /Void/ })).toHaveCount(0)

    // Check out to a brand-new external party.
    await page.getByRole('menuitem', { name: /Check out/ }).click()
    const checkOut = page.getByRole('dialog', { name: /Check out EV-/ })
    await checkOut.getByRole('radio', { name: 'New party' }).check({ force: true })
    await checkOut.getByLabel('Party name').fill('E2E Forensics Lab')
    await checkOut.getByLabel('Purpose').fill('Forensic imaging')
    await checkOut.getByRole('button', { name: 'Check out' }).click()

    // ...and acknowledge receipt right away.
    await checkOut.getByRole('button', { name: 'Acknowledge now' }).click()
    const ack = page.getByRole('dialog', { name: /Acknowledge receipt of EV-/ })
    await ack.getByLabel(/Full name/).fill('Lab Technician')
    await ack.getByRole('button', { name: 'Acknowledge' }).click()
    await expect(drawer.getByText('Acknowledged by Lab Technician')).toBeVisible()
    await expect(drawer.getByText(/Awaiting acknowledgment/)).toHaveCount(0)
    await expect(drawer.getByText('Checked out').first()).toBeVisible()

    // Check in.
    await drawer.getByRole('button', { name: /^Actions for EV-/ }).click()
    await page.getByRole('menuitem', { name: /Check in/ }).click()
    const checkIn = page.getByRole('dialog', { name: /Check in EV-/ })
    await checkIn.getByLabel('Storage location').fill('Evidence locker 2')
    await checkIn.getByLabel('Seal intact?').selectOption('yes')
    await checkIn.getByRole('button', { name: 'Check in' }).click()
    await expect(drawer.getByText('Stored at Evidence locker 2')).toBeVisible()

    // The chain verifies.
    await expect(drawer.getByRole('button', { name: /^Chain verified/ })).toBeVisible()
    const verify = await expectOk(await api.get(context, `/incidents/${incidentId}/evidence/custody/verify`), 'verify chain')
    expect(((await verify.json()) as { status: string }).status).toBe('intact')

    // Printable custody form (PDF).
    await drawer.getByRole('button', { name: /^Export EV-/ }).click()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('menuitem', { name: 'Printable custody form (PDF)' }).click(),
    ])
    expect(download.suggestedFilename()).toMatch(/\.pdf$/)
  })

  test('uploading a file registers an item with its hash', async ({ page }) => {
    await page.goto(`/dashboard/incidents/${incidentId}?tab=evidence`)
    await page.getByRole('button', { name: 'Upload file' }).click()
    const dialog = page.getByRole('dialog', { name: 'Upload files' })
    await dialog.getByLabel('Files to upload').setInputFiles({
      name: `e2e-${stamp()}.txt`,
      mimeType: 'text/plain',
      buffer: Buffer.from('evidence bytes'),
    })
    await dialog.getByRole('button', { name: 'Upload 1 file' }).click()
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('grid', { name: 'Evidence register' }).getByText(/e2e-.*\.txt/)).toBeVisible()
  })

  test('the legacy ?tab=artifacts link lands on the Evidence tab', async ({ page }) => {
    await page.goto(`/dashboard/incidents/${incidentId}?tab=artifacts`)
    await expect(page.getByRole('grid', { name: 'Evidence register' })).toBeVisible()
  })
})

test.describe('evidence: viewer gating', { tag: '@evidence' }, () => {
  useRole('viewer')

  test('a Viewer has no Evidence tab and ?tab=artifacts falls back to the overview', async ({ browser, page }) => {
    const owner = storageStatePath('responder', 'a')
    test.skip(!fs.existsSync(owner), 'needs the responder storage state to seed an incident')
    const ctx = await browser.newContext({ storageState: owner, baseURL: test.info().project.use.baseURL })
    let incidentId: string
    try {
      incidentId = await createIncident(ctx, `E2E evidence viewer ${stamp()}`, 'white')
      await registerItem(ctx, incidentId, 'Hidden from viewers')
    } finally {
      await ctx.close()
    }

    await page.goto(`/dashboard/incidents/${incidentId}?tab=artifacts`)
    await expect(page.getByRole('tab', { name: 'Evidence' })).toHaveCount(0)
    await expect(page.getByRole('grid', { name: 'Evidence register' })).toHaveCount(0)
    await expect(page.getByText('Hidden from viewers')).toHaveCount(0)
  })
})

test.describe('evidence: legal hold (administrator)', { tag: '@evidence' }, () => {
  useRole('admin')

  test('a held item cannot be disposed of until the hold is released', async ({ page, context }) => {
    test.setTimeout(90_000)
    const incidentId = await createIncident(context, `E2E evidence hold ${stamp()}`, 'green')
    await registerItem(context, incidentId, 'Held drive')

    await page.goto(`/dashboard/incidents/${incidentId}?tab=evidence`)
    await page.getByText('Held drive').click()
    const drawer = page.getByRole('dialog').filter({ hasText: 'Held drive' })

    // Place an indefinite hold.
    await drawer.getByRole('button', { name: /^Place legal hold on EV-/ }).click()
    const hold = page.getByRole('dialog', { name: 'Place legal hold' })
    await hold.getByLabel('Reason').fill('E2E matter 24-001')
    await hold.getByRole('button', { name: 'Place hold' }).click()
    await expect(drawer.getByText('Legal hold', { exact: true })).toBeVisible()

    // Dispose is disabled while held.
    await drawer.getByRole('button', { name: /^Actions for EV-/ }).click()
    await expect(page.getByRole('menuitem', { name: /Dispose/ })).toHaveAttribute('aria-disabled', 'true')
    await page.keyboard.press('Escape')

    // Release (with a confirmation), then dispose with the EV number typed.
    await drawer.getByRole('button', { name: /^Release legal hold on EV-/ }).click()
    await page.getByRole('dialog', { name: 'Release legal hold?' }).getByRole('button', { name: 'Release hold' }).click()
    await expect(drawer.getByText('No hold')).toBeVisible()

    await drawer.getByRole('button', { name: /^Actions for EV-/ }).click()
    await page.getByRole('menuitem', { name: /Dispose/ }).click()
    const dispose = page.getByRole('dialog', { name: /Dispose of EV-/ })
    await dispose.getByLabel('Reason').fill('Retention period over')
    await dispose.getByRole('button', { name: 'Dispose…' }).click()
    const confirm = page.getByRole('dialog', { name: /Dispose of EV-\d+\?/ })
    const number = (await drawer.getByText(/^EV-\d{4}$/).first().textContent()) ?? ''
    const go = confirm.getByRole('button', { name: 'Dispose', exact: true })
    await expect(go).toBeDisabled()
    await confirm.getByRole('textbox').fill(number.trim())
    await go.click()
    await expect(drawer.getByText('Disposed').first()).toBeVisible()
  })
})
